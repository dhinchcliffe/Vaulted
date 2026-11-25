"""Bounded web capture. Public IPs only, pinned DNS, redirects revalidated."""
import ipaddress,socket,ssl,http.client,re,time
from urllib.parse import urlsplit,urljoin
import markdownify
from bs4 import BeautifulSoup
from .storage import VaultError
MAX_BYTES=3*1024*1024

def safe_fetch(url, *, max_bytes=MAX_BYTES, image=False, timeout=15, deadline=None):
    for _ in range(6):
        if deadline is not None and time.monotonic() >= deadline: raise VaultError("Image capture timed out")
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise VaultError('Use a public HTTP or HTTPS URL')
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        if port not in (80,443):raise VaultError('Only standard web ports are supported')
        ips={a[4][0] for a in socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)}
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):raise VaultError('Private network URLs are not allowed')
        ip=sorted(ips)[0]
        sock=socket.create_connection((ip,port),timeout=timeout)
        try:
            if parsed.scheme=='https':sock=ssl.create_default_context().wrap_socket(sock,server_hostname=parsed.hostname)
            conn=http.client.HTTPConnection(parsed.hostname,port,timeout=timeout);conn.sock=sock
            conn.request('GET',(parsed.path or '/')+('?' + parsed.query if parsed.query else ''),headers={'Host':parsed.netloc,'User-Agent':'Vaulted/1.0 Research archive','Accept-Encoding':'identity'})
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):url=urljoin(url,response.getheader('Location',''));continue
            if response.status>=400:raise VaultError('The website refused this request',422)
            if not image and 'text/html' not in response.getheader('Content-Type',''):raise VaultError('This address is not an HTML page')
            data=bytearray()
            while True:
                if deadline is not None and time.monotonic() >= deadline: raise VaultError('Image capture timed out')
                chunk=response.read1(min(65536,max_bytes+1-len(data)))
                if not chunk: break
                data.extend(chunk)
                if len(data)>max_bytes:raise VaultError('Capture is too large')
            data=bytes(data)
            return data,url
        finally:sock.close()
    raise VaultError('Too many redirects')

def html_to_markdown(html):return markdownify.markdownify(html,heading_style='ATX')
def fetch_web_page(url):
    data,url=safe_fetch(url)
    soup=BeautifulSoup(data,'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else 'Untitled'
    main=soup.select_one('article,main,[role=main]') or soup
    for el in main.select('script,style,nav,footer,iframe,form,video,audio,source,object,embed'):el.decompose()
    for el in main.select('[href],[src]'):
        for attr in ('href','src'):
            if el.get(attr):el[attr]=urljoin(url,el[attr])
    return {'title':title,'url':url,'content':html_to_markdown(str(main))}
