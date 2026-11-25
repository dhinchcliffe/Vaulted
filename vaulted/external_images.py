"""Inspect one note locally; migrate only its image references, preserving prose."""
from dataclasses import dataclass
import html
from bisect import bisect_left
import re
import time
from urllib.parse import urlsplit, urljoin

from . import images
from .storage import VaultError


@dataclass
class Reference:
    start: int
    end: int
    url: str
    before: str
    after: str
    kind: str = 'markdown'

    def replacement(self, path):
        if self.kind == 'wiki': path = path.lstrip('/')
        if self.kind == 'html': path = '/api/attachment' + path
        return self.before + path + self.after


def mask_code(content):
    """Keep offsets while excluding examples, comments and non-rendered HTML."""
    masked = list(content)
    fence = None
    offset = 0
    for line in content.splitlines(keepends=True):
        opener = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if fence:
            masked[offset:offset+len(line)] = [c if c in '\r\n' else ' ' for c in line]
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*$', line): fence = None
        elif opener:
            fence = opener[1]
            masked[offset:offset+len(line)] = [c if c in '\r\n' else ' ' for c in line]
        offset += len(line)
    pattern = r'(?s)<!--.*?-->|<(script|style)\b[^>]*>.*?</\1\s*>|(?<!`)(`+)(?!`).*?(?<!`)\2(?!`)'
    for m in re.finditer(pattern, ''.join(masked), re.I):
        masked[m.start():m.end()] = [c if c in '\r\n' else ' ' for c in m[0]]
    # Markdown indented code blocks are not images either.
    for m in re.finditer(r'(?m)^(?: {4}|\t).+$', ''.join(masked)):
        masked[m.start():m.end()] = [c if c in '\r\n' else ' ' for c in m[0]]
    return ''.join(masked)


def source_origin(content):
    front = re.match(r'^---\s*\n([\s\S]*?)\n---\s*\n', content)
    m = re.search(r'^source_url:\s*(.+)$', front[1], re.M) if front else None
    if not m: m = re.search(r'\*Saved from\s+(https?://[^\s]+)\s+on', content, re.I)
    if not m: return ''
    try: p = urlsplit(m[1].strip())
    except ValueError: return ''
    return p.scheme+'://'+p.netloc if p.scheme in ('http','https') and p.netloc else ''


def external_references(content, origin=''):
    masked = mask_code(content)
    tag_pattern = r'<\/?[A-Za-z][\w-]*(?=[\s/>])(?:[^>\"\x27]|\"[^\"]*\"|\x27[^\x27]*\x27)*>'
    markdown = re.sub(tag_pattern, lambda m: ' '*len(m[0]), masked)
    source = source_origin(content)
    refs = []
    occupied = []
    local_hosts = {urlsplit(origin).hostname, 'vaulted-sable.vercel.app', 'vaulted-dhinchcliffes-projects.vercel.app'}

    def add(start, end, url, before='', after='', kind='markdown'):
        index = bisect_left(occupied,(start,end))
        if (index and occupied[index-1][1]>start) or (index<len(occupied) and occupied[index][0]<end): return
        # Escaped Markdown image syntax is literal text.
        slashes = 0
        while start-slashes>0 and content[start-slashes-1]=='\\': slashes+=1
        if kind != 'html' and slashes % 2: return
        url = html.unescape(url.strip())
        if url.startswith('/Attachments/Web/') or url.startswith('/api/attachment'): return
        if url.startswith('//'): url = 'https:' + url
        elif url.startswith('/') and kind == 'markdown' and source: url = urljoin(source,url)
        try:
            p=urlsplit(url)
            if p.scheme not in ('http','https') or not p.hostname or p.hostname in local_hosts: return
        except ValueError: return
        refs.append(Reference(start,end,url,before,after,kind));occupied.insert(index,(start,end))

    # Inline Markdown; the shared capture parser understands parentheses and titles.
    for start,end,u1,u2,url in images.image_links(markdown):
        add(start,end,url,content[start:u1],content[u2:end])
    for m in re.finditer(r'!\[\[([^\]\n]+)\]\]', markdown):
        url, separator, label = m[1].partition('|')
        add(m.start(),m.end(),url,'![[',separator+label+']]', 'wiki')
    # Expand image references in place; leave shared link definitions untouched.
    definitions={}
    for m in re.finditer(r'(?m)^ {0,3}\[([^\]\n]+)\]:\s*(<[^>\n]+>|\S+)(?:[ \t]+("[^"\n]*"|\x27[^\x27\n]*\x27))?[ \t]*$', markdown):
        definitions[' '.join(m[1].split()).casefold()] = (m[2].strip('<>'), (' '+m[3]) if m[3] else '')
    for m in re.finditer(r'!\[((?:\\.|[^\]\\\n])*)\](?:\[([^\]\n]*)\])?(?!\()',markdown):
        label = m[2] or m[1]
        entry=definitions.get(' '.join(label.split()).casefold())
        if entry: add(m.start(),m.end(),entry[0],'!['+m[1]+'](',entry[1]+')')

    attrs = re.compile(r'\s+(src|srcset)\s*=\s*(?:"([^"]*)"|\x27([^\x27]*)\x27|([^\s>]+))',re.I)
    lower = masked.lower()
    for m in re.finditer(r'<img\b(?:[^>\"\x27]|\"[^\"]*\"|\x27[^\x27]*\x27)*>',masked,re.I):
        tag=content[m.start():m.end()];found=list(attrs.finditer(tag));src='';srcset=''
        for attr in found:
            value=next(v for v in attr.groups()[1:] if v is not None)
            if attr[1].lower()=='src': src=value
            else: srcset=value
        # A picture/source or srcset can override src; archive a supplied rendition
        # and remove its remote alternatives only after a successful copy.
        pic_start=lower.rfind('<picture',0,m.start())
        pic_end=lower.find('</picture>',m.end())
        in_picture=pic_start>=0 and pic_end>=0 and '</picture>' not in lower[pic_start:m.start()]
        if in_picture:
            for source_tag in re.finditer(r'<source\b[^>]*>',content[pic_start:m.start()],re.I):
                for attr in attrs.finditer(source_tag[0]):
                    if attr[1].lower()=='srcset': srcset=next(v for v in attr.groups()[1:] if v is not None)
        if srcset:
            candidates=[v.strip().split()[0] for v in srcset.split(',') if v.strip()]
            remote=[v for v in candidates if v.startswith(('https://','http://','//'))]
            if remote: src=remote[-1]
        if not src: continue
        clean=attrs.sub('',tag)
        # Preserve unrelated attributes (alt, width, class) exactly.
        insertion=clean.rfind('/>') if clean.endswith('/>') else clean.rfind('>')
        before=clean[:insertion]+' src="';after='"'+clean[insertion:]
        start,end=m.start(),m.end()
        if in_picture:
            before=re.sub(r'<source\b[^>]*>','',content[pic_start:m.start()],flags=re.I)+before
            after+=content[m.end():pic_end+10];start,end=pic_start,pic_end+10
        add(start,end,src,before,after,'html')
    return sorted(refs,key=lambda r:r.start)


def external_image_count(content, origin=''):
    return len({r.url for r in external_references(content,origin)})


def migrate_batch(content, store_image, origin='', skip_urls=()):
    refs=external_references(content,origin)
    urls=list(dict.fromkeys(r.url for r in refs))
    pending=[u for u in urls if u not in set(skip_urls)]
    local={};failed=[];attempted=0;total=0;deadline=time.monotonic()+40
    for url in pending:
        if (attempted>=images.MAX_IMAGES or total+images.MAX_IMAGE_BYTES>images.MAX_TOTAL_BYTES
                or time.monotonic()>=deadline): break
        attempted+=1
        try:
            path,size=images.store_remote_image(url,store_image,images.MAX_IMAGE_BYTES,deadline)
            total+=size;local[url]=path
        except images.IMAGE_ERRORS:
            failed.append(url)
    for ref in reversed(refs):
        if ref.url in local:
            content=content[:ref.start]+ref.replacement(local[ref.url])+content[ref.end:]
    return {'content':content,'migrated':len(local),'failed_urls':failed,
            'remaining':len(urls)-len(local),'deferred':len(pending)-attempted}
