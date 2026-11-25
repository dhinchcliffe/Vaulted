"""Archive captured raster images as immutable, content-addressed vault attachments."""
import base64
import re
import time
import http.client
import requests
from urllib.parse import urlsplit

from .capture import safe_fetch
from .storage import VaultError

MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_IMAGES = 32


def image_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if data.startswith((b'GIF87a', b'GIF89a')): return 'image/gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return 'image/webp'
    if data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis'): return 'image/avif'
    raise VaultError('Unsupported image format; PNG, JPEG, WebP, GIF and AVIF are supported')


def image_links(markdown):
    """Locate inline images, including escaped/balanced parentheses and angle URLs.

    Capture's HTML-to-Markdown converter emits inline images. Keep all surrounding
    Markdown byte-for-byte, including alt text and optional titles.
    """
    pattern = re.compile(r'!\[(?:\\.|[^\]\\])*\]\(')
    for match in pattern.finditer(markdown):
        start = match.end()
        i = start
        while i < len(markdown) and markdown[i].isspace(): i += 1
        url_start = i
        if i < len(markdown) and markdown[i] == '<':
            end = markdown.find('>', i + 1)
            if end < 0: continue
            url = markdown[i + 1:end]
            i = end + 1
            url_end = i
        else:
            depth = 0
            while i < len(markdown):
                c = markdown[i]
                if c == '\\': i += 2; continue
                if c == '(' : depth += 1
                if c == ')':
                    if depth == 0: break
                    depth -= 1
                if c.isspace() and depth == 0: break
                i += 1
            url_end = i
            url = re.sub(r'\\([\\()])', r'\1', markdown[url_start:i])
        # Skip a quoted title, then the closing parenthesis.
        while i < len(markdown) and markdown[i].isspace(): i += 1
        if i < len(markdown) and markdown[i] in ('"', "'"):
            quote = markdown[i]; i += 1
            while i < len(markdown) and markdown[i] != quote:
                i += 2 if markdown[i] == '\\' else 1
            i += 1
            while i < len(markdown) and markdown[i].isspace(): i += 1
        if i < len(markdown) and markdown[i] == ')':
            yield match.start(), i + 1, url_start, url_end, url



IMAGE_ERRORS = (VaultError, OSError, ValueError, http.client.HTTPException, requests.RequestException)


def store_remote_image(url, store_image, max_bytes, deadline):
    data, _ = safe_fetch(url, max_bytes=max_bytes, image=True, timeout=4, deadline=deadline)
    mime = image_type(data)
    result = store_image(base64.b64encode(data).decode('ascii'), mime)
    return '/' + result['path'], len(data)


def archive_images(content, store_image):
    """Store before rewriting; failed images become source links, never remote embeds."""
    replacements = []
    cached = {}
    total = 0
    warnings = []
    deadline = time.monotonic() + 40
    for start, end, ustart, uend, url in image_links(content):
        if urlsplit(url).scheme not in ('https', 'http'): continue
        if url not in cached:
            try:
                if len(cached) >= MAX_IMAGES or total >= MAX_TOTAL_BYTES or time.monotonic() >= deadline:
                    raise VaultError('Capture image/time limit reached')
                cached[url], size = store_remote_image(url, store_image, min(MAX_IMAGE_BYTES, MAX_TOTAL_BYTES-total), deadline)
                total += size
            except IMAGE_ERRORS:
                cached[url] = None
                # Do not expose credentials or arbitrary upstream responses in the note.
                warnings.append('An image could not be archived; its original link is retained below.')
        local = cached[url]
        if local:
            replacement = content[start:ustart] + local + content[uend:end]
        else:
            replacement = '[Image not archived — original source](<' + url.replace('>', '%3E') + '>)'
        replacements.append((start, end, replacement))
    for start, end, replacement in reversed(replacements):
        content = content[:start] + replacement + content[end:]
    if warnings:
        content += '\n\nCapture note: ' + str(len(warnings)) + ' image(s) could not be archived. Original image links are retained for follow-up.\n'
    return content, warnings
