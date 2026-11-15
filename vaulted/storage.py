"""User-scoped Supabase repository. No privileged key is used by the web app."""
import os,posixpath
import requests
from urllib.parse import quote

class VaultError(Exception):
    def __init__(self,message,status=400): self.message,self.status=message,status

def valid_path(value,allow_root=False):
    if not isinstance(value,str) or '\x00' in value or '\\' in value or value.startswith('/') or '..' in value.split('/'):
        raise VaultError('Invalid vault path')
    value=posixpath.normpath(value)
    if value=='.':
        if allow_root:return ''
        raise VaultError('A file path is required')
    if any(p.startswith('.') for p in value.split('/')): raise VaultError('Hidden vault metadata is read-only',403)
    return value

class SupabaseVault:
    def __init__(self,token):
        self.url=os.environ['SUPABASE_URL'].rstrip('/')
        self.headers={'apikey':os.environ['SUPABASE_PUBLISHABLE_KEY'],'Authorization':'Bearer '+token}
    def call(self,method,path,**kw):
        headers={**self.headers,**kw.pop('headers',{})}
        r=requests.request(method,self.url+path,headers=headers,timeout=45,**kw)
        if not r.ok:
            try:msg=r.json().get('message') or r.json().get('error') or 'Storage operation failed'
            except ValueError:msg='Storage operation failed'
            raise VaultError(msg,r.status_code if r.status_code in (400,401,403,404,409,429) else 502)
        return r
    def rows(self):
        out=[]
        while True:
            batch=self.call('GET','/rest/v1/vault_files',params={'select':'id,path,revision,size,mime,object_key','order':'path','offset':len(out),'limit':1000}).json()
            out.extend(batch)
            if len(batch)<1000:return out
    def get(self,path):
        rows=self.call('GET','/rest/v1/vault_files',params={'path':'eq.'+path,'select':'*','limit':1}).json()
        if not rows:raise VaultError('File not found',404)
        return rows[0]
    def save(self,path,content,revision):
        return self.call('POST','/rest/v1/rpc/vault_save',json={'p_path':valid_path(path),'p_content':content,'p_revision':revision}).json()
    def create(self,path,content):
        return self.call('POST','/rest/v1/vault_files',json={'path':valid_path(path),'content':content,'mime':'text/markdown','size':len(content.encode())},headers={'Prefer':'return=representation'}).json()[0]
    def move(self,source,target):
        return self.call('POST','/rest/v1/rpc/vault_move',json={'p_from':valid_path(source),'p_to':valid_path(target)}).json()
    def search(self,query):
        return self.call('POST','/rest/v1/rpc/vault_search',json={'p_query':query}).json()
    def download(self,row):
        r=self.call('GET','/storage/v1/object/authenticated/vault-original/'+quote(row['object_key'],safe='/'))
        return r.content

def build_tree(rows):
    root={}
    for row in rows:
        path=row['path']
        if not path.endswith('.md') or any(x.startswith('.') for x in path.split('/')):continue
        parts=path.split('/');node=root
        for i,name in enumerate(parts):
            if i==len(parts)-1:node[name]={'name':name,'path':path,'type':'file'}
            else:node=node.setdefault(name,{'name':name,'path':'/'.join(parts[:i+1]),'type':'directory','_children':{}})['_children']
    def finish(node):
        values=list(node.values())
        for v in values:
            if '_children' in v:v['children']=finish(v.pop('_children'))
        return sorted(values,key=lambda v:(v['type']!='directory',v['name'].lower()))
    return finish(root)
