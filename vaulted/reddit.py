"""Best-effort public Reddit capture. No cookies, credentials, comments or video."""
import html
import json
import re
import time
from urllib.parse import urlsplit, urljoin

import requests

from .translation import plain_markdown

HOSTS = {'reddit.com', 'www.reddit.com', 'old.reddit.com', 'new.reddit.com',
         'np.reddit.com', 'm.reddit.com', 'sh.reddit.com', 'redd.it', 'www.redd.it'}
IMAGE_HOSTS = {'i.redd.it', 'preview.redd.it', 'external-preview.redd.it'}


def reddit_url(url):
    try:
        p = urlsplit(url)
        return (p.scheme in ('http', 'https') and p.hostname in HOSTS
                and not p.username and not p.password and p.port in (None, 80, 443))
    except ValueError:
        return False


def post_id(url):
    if not reddit_url(url):
        return None
    p = urlsplit(url)
    pattern = (r'/([a-z0-9]{4,12})/?' if p.hostname in {'redd.it', 'www.redd.it'}
               else r'/(?:r/[^/]+/)?(?:comments|gallery)/([a-z0-9]{4,12})(?:/.*)?')
    match = re.fullmatch(pattern, p.path, re.I)
    return match.group(1).lower() if match else None


def _get(url, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError('Reddit retrieval timed out')
    return requests.get(url, headers={'User-Agent': 'Vaulted/1.2 (personal research capture)'},
                        timeout=(min(5, remaining), min(12, remaining)),
                        stream=True, allow_redirects=False)


def resolve_post(url, deadline):
    # Native-app /s/ links and redd.it links stay on an explicit host allowlist.
    # Never follow a redirect to a user-controlled article or a private address.
    for _ in range(5):
        if not reddit_url(url):
            raise ValueError('Not a Reddit post URL')
        identifier = post_id(url)
        if identifier:
            return identifier
        if not re.fullmatch(r'/(?:r/[^/]+/)?s/[A-Za-z0-9]+/?', urlsplit(url).path):
            raise ValueError('Not a Reddit post URL')
        response = _get(url, deadline)
        try:
            if response.status_code not in (301, 302, 303, 307, 308):
                raise ValueError('Reddit share link unavailable')
            url = urljoin(url, response.headers.get('Location', ''))
        finally:
            response.close()
    raise ValueError('Too many Reddit redirects')


def _image(url):
    url = html.unescape(url) if isinstance(url, str) else ''
    try:
        p = urlsplit(url)
        return url if (p.scheme == 'https' and p.hostname in IMAGE_HOSTS
                       and not p.username and not p.password and p.port in (None, 443)
                       and not re.search(r'[<>\s]', url)) else ''
    except ValueError:
        return ''


def fetch_reddit_post(url):
    deadline = time.monotonic() + 30
    identifier = resolve_post(url, deadline)
    response = _get('https://www.reddit.com/comments/' + identifier
                    + '.json?raw_json=1&limit=0', deadline)
    try:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 2_000_000 or time.monotonic() > deadline:
                raise ValueError('Reddit response exceeded capture limits')
        payload = json.loads(data)
    finally:
        response.close()
    return parse_reddit_post(payload, identifier)


def parse_reddit_post(payload, identifier):
    """Parse fetched or phone-supplied data; identity must match the source URL."""
    if not identifier:
        raise ValueError('A canonical Reddit post URL is required')
    listing = payload[0] if isinstance(payload, list) and payload else payload
    children = listing['data']['children']
    post = next((item['data'] for item in children
                 if item.get('kind') == 't3' and item.get('data', {}).get('id') == identifier), None)
    if not post or not isinstance(post.get('title'), str):
        raise ValueError('Reddit post unavailable')
    text = post.get('selftext') or ''
    if not isinstance(text, str) or text in ('[removed]', '[deleted]'):
        raise ValueError('Reddit post removed or unavailable')
    photos = []
    seen = set()

    def add_image(url, caption='Post image'):
        url = _image(url)
        if url and url not in seen:
            seen.add(url)
            photos.append('![' + plain_markdown(str(caption)).replace('\n', ' ') + '](<' + url + '>)')

    metadata = post.get('media_metadata') or {}
    # Reddit rich-text posts reference inline media by ID, not a usable URL.
    def inline_image(match):
        media = metadata.get(match.group(2), {})
        image = _image((media.get('s') or {}).get('u'))
        if media.get('e') == 'Image' and media.get('status') == 'valid' and image:
            return '![' + match.group(1) + '](<' + image + '>)'
        return match.group(0)

    text = re.sub(r'!\[([^\]\n]*)\]\(([A-Za-z0-9_]+)\)', inline_image, text)
    for item in (post.get('gallery_data') or {}).get('items', [])[:32]:
        media = metadata.get(item.get('media_id'), {})
        if media.get('e') == 'Image' and media.get('status') == 'valid':
            add_image((media.get('s') or {}).get('u'), item.get('caption') or 'Post image')
    destination = post.get('url_overridden_by_dest') or post.get('url') or ''
    if not post.get('is_video'):
        add_image(destination)
    article_url = ''
    if not post.get('is_self') and not post.get('is_video') and not photos:
        p = urlsplit(destination)
        if (p.scheme in ('http', 'https') and p.hostname and not p.username and not p.password
                and p.port in (None, 80, 443) and not reddit_url(destination)
                and p.hostname not in IMAGE_HOSTS | {'v.redd.it'}
                and not re.search(r'\.(?:mp4|webm|mov|m3u8)(?:$|\?)', destination, re.I)):
            article_url = destination
    return {'title': post['title'], 'text': text, 'photos': photos,
            'author': str(post.get('author') or 'unknown'),
            'subreddit': str(post.get('subreddit') or ''), 'article_url': article_url,
            'url': 'https://www.reddit.com/comments/' + identifier + '/',
            'video': bool(post.get('is_video'))}
