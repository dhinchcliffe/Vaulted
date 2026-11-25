from flask import Flask
from vaulted.auth import install_auth
from vaulted.storage import VaultError

def client(monkeypatch):
    monkeypatch.setenv('VERCEL','1')
    monkeypatch.setenv('SESSION_SECRET','test-only')
    app=Flask(__name__)
    install_auth(app)
    app.add_url_rule('/probe',endpoint='health',view_func=lambda:'OK',methods=['POST'])
    app.add_url_rule('/api/probe',endpoint='health',methods=['POST'])
    app.register_error_handler(VaultError,lambda e:(e.message,e.status))
    return app.test_client()

def test_form_token_handles_proxy_and_browser_origins(monkeypatch):
    c=client(monkeypatch)
    with c.session_transaction(base_url='https://internal.example') as s:s['csrf_token']='session-token'
    for origin in ('https://vaulted-sable.vercel.app','null'):
        assert c.post('/probe',base_url='https://internal.example',data={'csrf_token':'session-token'},headers={'Origin':origin}).status_code==200

def test_missing_or_wrong_form_token_rejected(monkeypatch):
    c=client(monkeypatch)
    with c.session_transaction(base_url='https://internal.example') as s:s['csrf_token']='session-token'
    for token in ('','other-session-token'):
        assert c.post('/probe',base_url='https://internal.example',data={'csrf_token':token}).status_code==403

def test_api_canonical_origin_and_foreign_origin(monkeypatch):
    c=client(monkeypatch)
    for origin,expected in [('https://vaulted-sable.vercel.app',200),('https://evil.example',403),('null',403),('https://vaulted-sable.vercel.app.evil.example',403)]:
        assert c.post('/api/probe',base_url='https://internal.example',headers={'Origin':origin,'X-Vaulted-Request':'1'}).status_code==expected
    assert c.post('/api/probe',base_url='https://internal.example',headers={'Origin':'https://vaulted-sable.vercel.app'}).status_code==403
