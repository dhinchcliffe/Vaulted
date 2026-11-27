"""Normalize share-sheet captures; public X enrichment is best effort, never video."""
import json
import http.client
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin

import requests
from bs4 import BeautifulSoup

from .capture import fetch_web_page, html_to_markdown
from .storage import VaultError
from .reddit import reddit_url, fetch_reddit_post, parse_reddit_post, post_id as reddit_post_id
from .translation import translate_x_text, plain_markdown

MAX_TEXT = 700_000
X_HOSTS = {'x.com', 'www.x.com', 'mobile.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com'}


def public_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise VaultError('Invalid source URL')
    try:
        p = urlsplit(value.strip())
        if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
            raise ValueError()
        if p.port and p.port not in (80, 443):
            raise ValueError()
    except ValueError:
        raise VaultError('Use an HTTP or HTTPS source URL')
    return value.strip()


def x_post_id(url):
    p = urlsplit(url)
    if p.hostname not in X_HOSTS:
        return None
    match = re.fullmatch(r'/(?:[^/]+/status|i/web/status|i/status)/(\d{5,30})/?(?:photo/\d+)?', p.path)
    return match.group(1) if match else None


def clean_html(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    for el in soup.select('script,style,nav,footer,iframe,form,video,audio,source,object,embed,input,button'):
        el.decompose()
    for el in soup.select('[href],[src]'):
        for attr in ('href', 'src'):
            if el.get(attr):
                target = urljoin(url, el[attr])
                if urlsplit(target).scheme in ('http', 'https'):
                    el[attr] = target
                else:
                    del el[attr]
    for el in soup.select('img'):
        if not el.get('src'):
            el.decompose()
    return html_to_markdown(str(soup)).strip()


def fetch_x_post(post_id, translate_to=None):
    # Only the public post ID is sent to FxTwitter. No vault data, cookies or tokens.
    response = requests.get('https://api.fxtwitter.com/status/' + post_id + ('/en' if translate_to == 'en' else ''),
                            headers={'User-Agent': 'Vaulted/1.1 Research capture'},
                            timeout=(5, 15), stream=True, allow_redirects=False)
    try:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 2_000_000:
                raise ValueError('X response too large')
        payload = json.loads(data)
    finally:
        response.close()
    tweet = payload.get('tweet') or payload.get('status') or {}
    if payload.get('code') != 200 or str(tweet.get('id')) != post_id:
        raise ValueError('Post unavailable')
    raw = tweet.get('raw_text') or {}
    text = max((s for s in [tweet.get('text'), raw.get('text')] if isinstance(s, str)), key=len, default='')
    if not text.strip():
        raise ValueError('No post text returned')
    photos = []
    for photo in (tweet.get('media') or {}).get('photos', [])[:12]:
        if photo.get('type', 'photo') != 'photo':
            continue
        image = photo.get('url', '')
        p = urlsplit(image)
        if p.scheme == 'https' and p.hostname == 'pbs.twimg.com':
            alt = str(photo.get('altText') or 'Post image').replace('[', '').replace(']', '').replace('\n', ' ')
            photos.append(f'![{alt}](<{image}>)')
    author = tweet.get('author') or {}
    name = author.get('name') or author.get('screen_name') or 'X'
    return {'text': text, 'photos': photos, 'author': str(name),
            'lang': tweet.get('lang') or '', 'translation': tweet.get('translation')}


def normalize_payload(data):
    if not isinstance(data, dict):
        raise VaultError('Send a JSON object')
    payload = data.get('payload', data)
    if isinstance(payload, str):
        if len(payload.encode()) > 1_000_000:
            raise VaultError('Shared page is too large. Share a selection instead.', 413)
        try:
            decoded = json.loads(payload)
        except ValueError:
            decoded = None
        payload = decoded if isinstance(decoded, dict) else {'text': payload}
    if not isinstance(payload, dict):
        raise VaultError('Unsupported shared content')
    for key in ('url', 'title', 'text', 'html', 'reddit_json'):
        if key in payload and not isinstance(payload[key], str):
            raise VaultError('Invalid shared ' + key)
    if sum(len(payload.get(k, '').encode()) for k in ('url', 'title', 'text', 'html', 'reddit_json')) > 1_000_000:
        raise VaultError('Shared page is too large. Share a selection instead.', 413)
    text = payload.get('text', '')
    url = payload.get('url', '')
    if not url:
        urls = re.findall(r'https?://[^\s<>"\uFFFC]+', text)
        url = next((u for u in urls if x_post_id(u) or reddit_url(u)), urls[0] if urls else '')
    if url:
        payload['url'] = public_url(url)
    if 'reddit_json' in payload and not reddit_post_id(url):
        raise VaultError('Phone capture requires a Reddit post URL', 422)
    if not url and not text.strip() and not payload.get('html', '').strip():
        raise VaultError('Share a webpage, Reddit or X post link, or selected text')
    return payload


def build_note(payload):
    url = payload.get('url', '')
    text = payload.get('text', '').strip()
    html = payload.get('html', '')
    title = payload.get('title', '').strip()
    warnings = []
    body = clean_html(html, url) if html else text
    post_id = x_post_id(url) if url else None
    method = 'Shared page' if html else 'Shared text'
    if post_id:
        canonical = f'https://x.com/i/status/{post_id}'
        translation_source = BeautifulSoup(html, 'html.parser').get_text('\n', strip=True) if html else text
        translation_language = ''
        translation_lookup = None
        author = 'X'
        try:
            post = fetch_x_post(post_id)
            author = post['author']
            # Prefer fuller text captured in Safari when the public service is truncated.
            supplied_text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True) if html else text
            if len(supplied_text) > len(post['text']) and supplied_text != url:
                body = body + '\n\n' + '\n\n'.join(post['photos'])
                method = 'Shared content with public X image enrichment'
            else:
                body = post['text'] + '\n\n' + '\n\n'.join(post['photos'])
                method = 'Public X post via FxTwitter'
                translation_source = post['text']
                translation_language = post.get('lang', '')
                translation_lookup = lambda: fetch_x_post(post_id, translate_to='en')
            title = title or f"{post['author']} — {post['text'].splitlines()[0][:90]}"
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            warnings.append('X retrieval was unavailable. Shared text was kept; for the full post, open it in Safari, expand the text and share again.')
            if not body or body == url:
                body = 'Post content could not be retrieved. The source link is saved for follow-up.'
                title = title or f'X post {post_id}'
        if translation_source.strip() and translation_source.strip() != url:
            translated, translation_warning = translate_x_text(translation_source, translation_language, translation_lookup)
            if translated:
                translated_body = ('## English translation\n\n' + plain_markdown(translated['text'])
                        + '\n\nTranslation: ' + translated['provider'] + ' · ' + translated['language']
                        + ' → English. Wording may differ from X’s displayed translation.\n\n'
                        + '## Original captured content\n\n' + body)
                if len(translated_body.encode()) <= MAX_TEXT:
                    body = translated_body
                    title = f"{author} — {translated['text'].splitlines()[0][:90]}"
                else:
                    warnings.append('English translation exceeded the note size limit. The complete original was saved.')
            elif translation_warning:
                warnings.append(translation_warning)
        url = canonical
    elif url and reddit_url(url):
        try:
            if 'reddit_json' in payload:
                post = parse_reddit_post(json.loads(payload['reddit_json']), reddit_post_id(url))
            else:
                post = fetch_reddit_post(url)
            title = post['title']
            # Keep Safari's richer selection alongside the structured post rather
            # than silently replacing either source. Native shares usually only carry a URL.
            supplied = body if body and body != url else ''
            body = post['text']
            if supplied and supplied.strip() not in (body.strip(), title.strip()) and supplied.strip() not in body:
                body += '\n\n## Shared content\n\n' + supplied
            body += '\n\n' + '\n\n'.join(post['photos'])
            body = ('Posted by ' + plain_markdown(post['author']) + ' in r/'
                    + plain_markdown(post['subreddit']) + '\n\n' + body)
            url = post['url']
            method = 'Reddit post fetched on iPhone' if 'reddit_json' in payload else 'Public Reddit post'
            if post['video']:
                warnings.append('This post contains video. Video was not imported.')
            if post['article_url']:
                article_url = public_url(post['article_url'])
                body += '\n\nArticle source: ' + article_url
                try:
                    article = fetch_web_page(article_url)
                    body += '\n\n## Linked article\n\n' + article['content']
                except (VaultError, OSError, ValueError, requests.RequestException, http.client.HTTPException):
                    warnings.append('The linked article could not be retrieved. Its source URL was kept.')
        except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError, IndexError):
            if 'reddit_json' in payload:
                raise VaultError('Reddit did not return a readable post to the phone. Nothing was saved. Please report the error from this test; your original Shortcut is unchanged.', 422)
            warnings.append('Reddit retrieval was unavailable. Shared content was kept. Open the post in Safari and share its visible content or selected text if needed.')
            if not body or body == url:
                body = 'Post content could not be retrieved. The source link is saved for follow-up.'
                title = title or 'Reddit post'
    elif url and not html and (not text or text == url):
        try:
            page = fetch_web_page(url)
            body = page['content']
            title = title or page['title']
            method = 'Fetched public webpage'
        except (VaultError, OSError, ValueError):
            body = 'Page content could not be retrieved. The source link is saved for follow-up.'
            warnings.append('Open the page in Safari and share again to capture its visible content.')
    title = title or next((s.strip('# ').strip() for s in body.splitlines() if s.strip()), 'Shared note')
    title = re.sub(r'[\x00-\x1f\\/:*?"<>|]', '', title).strip().strip('.')[:120] or 'Shared note'
    if len(body.encode()) > MAX_TEXT:
        raise VaultError('Captured content is too large. Share a selection instead.', 413)
    warning_text = '\n\n'.join('Capture note: ' + w for w in warnings)
    source = f'Source: {url}\n\n' if url else ''
    note = f'# {title}\n\n{source}Saved: {datetime.now(timezone.utc).isoformat()}\n\n{body.strip()}\n\n{warning_text}\n\nCapture method: {method}\n'
    return {'title': title, 'content': note, 'warnings': warnings}
