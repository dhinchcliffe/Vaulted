// Runs only when the user invokes Save to Vaulted from Safari's share sheet.
(() => {
  const url = location.href;
  const postId = /\/(?:[^/]+\/status|i\/web\/status|i\/status)\/(\d+)/.exec(location.pathname)?.[1];
  const isX = /(^|\.)(x|twitter)\.com$/.test(location.hostname);
  let root;
  if (isX && postId) {
    root = [...document.querySelectorAll('article')].find(article =>
      [...article.querySelectorAll('a[href]')].some(a => a.getAttribute('href').split('?')[0].endsWith('/status/' + postId)));
  }
  root = root || document.querySelector('article') || document.querySelector('main,[role=main]') || document.body;
  const clone = root.cloneNode(true);
  const originalImages = root.querySelectorAll('img');
  clone.querySelectorAll('img').forEach((img, index) => {
    const original = originalImages[index];
    const src = original.currentSrc || original.src || original.getAttribute('data-src');
    if (!src || !/^https?:/.test(src) || (isX && !src.includes('pbs.twimg.com/media/'))) {
      img.remove(); return;
    }
    img.setAttribute('src', src);
    img.removeAttribute('srcset');
  });
  clone.querySelectorAll('a[href]').forEach(a => {
    try { a.setAttribute('href', new URL(a.getAttribute('href'), url).href); } catch (_) { a.removeAttribute('href'); }
  });
  clone.querySelectorAll('script,style,nav,footer,iframe,form,video,audio,source,object,embed,button,input,[role=button]').forEach(el => el.remove());
  // Remove inline handlers and irrelevant large attributes before transferring.
  clone.querySelectorAll('*').forEach(el => [...el.attributes].forEach(attr => {
    if (!['href', 'src', 'alt', 'title'].includes(attr.name)) el.removeAttribute(attr.name);
  }));
  const payload = {url, title: document.title, html: clone.innerHTML};
  if (payload.html.length > 700000) {
    completion(JSON.stringify({url, title: document.title, text: root.innerText.slice(0, 500000) + '\n\nCapture note: Large page saved as text; images omitted.'}));
  } else completion(JSON.stringify(payload));
})();
