"""Vaulted HTTP interface; persistence, authentication, capture are separate modules."""
import os,re,posixpath,mimetypes
from datetime import datetime,timezone
from flask import Flask,render_template,jsonify,request,g,Response,redirect
from vaulted.auth import install_auth
from vaulted.storage import VaultError,valid_path,build_tree
from vaulted.capture import fetch_web_page,html_to_markdown
from vaulted.filing import existing_folders,resolve_folder,suggest_folder
from vaulted.sharing import bp as sharing_bp
from vaulted.images import archive_images
from vaulted.external_images import external_image_count, migrate_batch
app=Flask(__name__,static_folder='public/static',static_url_path='/static')
install_auth(app)
app.register_blueprint(sharing_bp)
@app.errorhandler(VaultError)
def vault_error(e):return jsonify(error=e.message),e.status
@app.errorhandler(Exception)
def unexpected(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e,HTTPException):return jsonify(error=e.description),e.code
    app.logger.error('Request failed: %s',type(e).__name__)
    return jsonify(error='The operation could not be completed. Your original files are safe.'),500
@app.after_request
def headers(r):
    r.headers['Cache-Control']='no-store'
    r.headers['X-Content-Type-Options']='nosniff'
    r.headers['X-Frame-Options']='DENY'
    r.headers['Referrer-Policy']='no-referrer'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    return r
@app.get('/health')
def health():return jsonify(status='ok',version='1.1-ios-share')
@app.get('/')
def index():return render_template('index.html')
@app.get('/api/tree')
def tree():return jsonify(build_tree(g.vault.rows()))
@app.get('/api/status')
def status():
    rows=g.vault.rows();n=sum(r['path'].endswith('.md') for r in rows)
    return jsonify(total_markdown_files=n,accessible_files=n,total_files=len(rows),sync_status='synced',vault_path='DPH Research')
@app.get('/api/first')
def first():return jsonify(path=next((r['path'] for r in g.vault.rows() if r['path'].endswith('.md')),None))
@app.get('/api/file')
def get_file():
    row=g.vault.get(valid_path(request.args.get('path','')))
    if row['content'] is None:raise VaultError('Not a Markdown document')
    return jsonify(content=row['content'],path=row['path'],revision=row['revision'],
                   external_image_count=external_image_count(row['content'],request.host_url))
@app.post('/api/file')
def save_file():
    d=request.get_json()
    if not isinstance(d.get('content'),str) or not isinstance(d.get('revision'),int):raise VaultError('Content and revision are required')
    result=g.vault.save(d.get('path',''),d['content'],d['revision'])
    return jsonify(**result,external_image_count=external_image_count(d['content'],request.host_url))
@app.post('/api/migrate-images')
def migrate_images():
    d=request.get_json(silent=True)
    if not isinstance(d,dict) or type(d.get('revision')) is not int:
        raise VaultError('Page revision is required')
    path=valid_path(d.get('path',''))
    skip=d.get('skip_urls',[])
    if not isinstance(skip,list) or len(skip)>1000 or any(not isinstance(u,str) or len(u)>4096 for u in skip):
        raise VaultError('Invalid retry state')
    row=g.vault.get(path)
    if row['content'] is None:raise VaultError('Choose a Markdown page')
    if row['revision']!=d['revision']:
        raise VaultError('This page changed. Reload it before migrating images.',409)
    result=migrate_batch(row['content'],g.vault.store_image,request.host_url,skip)
    revision=row['revision']
    if result['content']!=row['content']:
        # Atomic compare-and-swap protects edits or moves made during downloads.
        revision=g.vault.save(path,result['content'],revision)['revision']
    app.logger.info('image_migration migrated=%d remaining=%d',result['migrated'],result['remaining'])
    return jsonify(success=True,path=path,revision=revision,**result)

@app.get('/api/search')
def search():
    q=request.args.get('q','').strip()[:200]
    if not q:raise VaultError('Enter a search term')
    rows=g.vault.search(q);return jsonify(query=q,results=rows,count=len(rows))
@app.get('/api/attachment')
@app.get('/api/attachment/<path:filepath>')
def attachment(filepath=None):
    filepath=filepath if filepath is not None else request.args.get('path','')
    paths=[];origin=request.args.get('from','')
    if '/' in filepath:paths.append(filepath)
    if origin:paths.append(posixpath.normpath(posixpath.join(posixpath.dirname(origin),filepath)))
    paths.append(filepath)
    for p in dict.fromkeys(paths):
        try:row=g.vault.get(valid_path(p))
        except VaultError as e:
            if e.status in (400,404):continue
            raise
        if row['content'] is None and row.get('object_key') and row['size']>3*1024*1024:
            return redirect(g.vault.download_url(row))
        data=row['content'].encode() if row['content'] is not None else g.vault.download(row)
        mime=row['mime'];r=Response(data,mimetype=mime)
        if mime not in ('image/png','image/jpeg','image/gif','image/webp','image/avif','application/pdf'):
            r.headers['Content-Disposition']='attachment'
        return r
    raise VaultError('Attachment not found',404)

def clean_name(value):
    value=re.sub(r'[\\/:*?"<>|\x00-\x1f]','',value).strip().strip('.')[:160]
    if not value:raise VaultError('Enter a valid name')
    return value

def create_unique(folder,name,content):
    folder=valid_path(folder,True);name=clean_name(name)
    for n in range(100):
        stem,ext=posixpath.splitext(name);candidate=name if n==0 else f'{stem} ({n}){ext}'
        path=posixpath.join(folder,candidate)
        try:g.vault.create(path,content);return path
        except VaultError as e:
            if e.status!=409:raise
    raise VaultError('Too many files with the same name',409)
@app.post('/api/create-page')
def create_page():
    d=request.get_json();name=clean_name(d.get('filename',''))
    if not name.endswith('.md'):name+='.md'
    path=posixpath.join(valid_path(d.get('folder',''),True),name)
    g.vault.create(path,f'---\ncreated: {datetime.now(timezone.utc).date()}\n---\n\n# {name[:-3]}\n\n')
    return jsonify(success=True,path=path,filename=name)
@app.post('/api/quick-paste')
def paste():
    d=request.get_json();content=d.get('content','')
    if not isinstance(content,str) or not content.strip():raise VaultError('Paste some content first')
    if d.get('is_html'):content=html_to_markdown(content)
    content,_=archive_images(content,g.vault.store_image)
    title=clean_name(re.sub(r'^#+\s*','',content.splitlines()[0])[:100] or 'Quick Paste')
    now=datetime.now(timezone.utc)
    path=create_unique('ReadItLater Inbox',f'{title} - {now.date()}.md',f'---\ncreated: {now.isoformat()}\n---\n\n[[ReadItLater]] [[Quick Paste]]\n\n{content}\n')
    return jsonify(success=True,path=path,title=title)
@app.post('/api/fetch-web')
def capture():
    url=request.get_json().get('url','').strip()
    if not url:raise VaultError('Enter a URL')
    if '://' not in url:url='https://'+url
    result=fetch_web_page(url);now=datetime.now(timezone.utc)
    title=clean_name(result['title'][:100]);content=f"# [{title}]({result['url']})\n\n{result['content']}\n\nSource: {result['url']}\nSaved: {now.isoformat()}\n"
    content,_=archive_images(content,g.vault.store_image)
    path=create_unique('ReadItLater Inbox',f'{title} - {now.date()}.md',content)
    return jsonify(success=True,path=path,title=title)
@app.post('/api/rename')
def rename():
    d=request.get_json();source=valid_path(d.get('path',''));name=clean_name(d.get('new_name',''))
    return jsonify(g.vault.move(source,posixpath.join(posixpath.dirname(source),name)))
@app.post('/api/move-file')
def move():
    d=request.get_json();source=valid_path(d.get('from_path',''))
    target=resolve_folder(d.get('to_folder',''),existing_folders(g.vault.rows()))
    destination=posixpath.join(target,posixpath.basename(source))
    if destination==source:
        g.vault.get(source)
        return jsonify(success=True,new_path=source,count=0)
    return jsonify(g.vault.move(source,destination))
@app.post('/api/suggest-file-location')
def suggest():
    d=request.get_json();path=valid_path(d.get('path',''))
    content=d.get('content')
    if not isinstance(content,str) or not content:content=g.vault.get(path)['content']
    if not isinstance(content,str):raise VaultError('Choose a Markdown document')
    return jsonify(suggest_folder(content,path,existing_folders(g.vault.rows())))
if __name__=='__main__':app.run(port=5006,debug=False)
