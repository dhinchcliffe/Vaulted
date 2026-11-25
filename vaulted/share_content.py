"""Normalize share-sheet captures; public X enrichment is best effort, never video."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin

import requests
from bs4 import BeautifulSoup

from .capture import fetch_web_page, html_to_markdown
from .storage import VaultError

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


def fetch_x_post(post_id):
    # Only the public post ID is sent to FxTwitter. No vault data, cookies or tokens.
    response = requests.get('https://api.fxtwitter.com/status/' + post_id,
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
    return {'text': text, 'photos': photos, 'author': str(name)}


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
    for key in ('url', 'title', 'text', 'html'):
        if key in payload and not isinstance(payload[key], str):
            raise VaultError('Invalid shared ' + key)
    if sum(len(payload.get(k, '').encode()) for k in ('url', 'title', 'text', 'html')) > 1_000_000:
        raise VaultError('Shared page is too large. Share a selection instead.', 413)
    text = payload.get('text', '')
    url = payload.get('url', '')
    if not url:
        urls = re.findall(r'https?://[^\s<>"\uFFFC]+', text)
        url = next((u for u in urls if x_post_id(u)), urls[0] if urls else '')
    if url:
        payload['url'] = public_url(url)
    if not url and not text.strip() and not payload.get('html', '').strip():
        raise VaultError('Share a webpage, X post link or selected text')
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
        try:
            post = fetch_x_post(post_id)
            # Prefer fuller text captured in Safari when the public service is truncated.
            supplied_text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True) if html else text
            if len(supplied_text) > len(post['text']) and supplied_text != url:
                body = body + '\n\n' + '\n\n'.join(post['photos'])
                method = 'Shared content with public X image enrichment'
            else:
                body = post['text'] + '\n\n' + '\n\n'.join(post['photos'])
                method = 'Public X post via FxTwitter'
            title = title or f"{post['author']} — {post['text'].splitlines()[0][:90]}"
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            warnings.append('X retrieval was unavailable. Shared text was kept; for the full post, open it in Safari, expand the text and share again.')
            if not body or body == url:
                body = 'Post content could not be retrieved. The source link is saved for follow-up.'
                title = title or f'X post {post_id}'
        url = canonical
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
