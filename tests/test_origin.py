from flask import Flask
from vaulted.auth import install_auth
from vaulted.storage import VaultError

def client(monkeypatch, deployed=True):
    if deployed: monkeypatch.setenv('VERCEL','1')
    else: monkeypatch.delenv('VERCEL',raising=False)
    monkeypatch.setenv('SESSION_SECRET','test-only')
    app=Flask(__name__)
    install_auth(app)
    app.add_url_rule('/probe',endpoint='health',view_func=lambda:'OK',methods=['POST'])
    app.register_error_handler(VaultError,lambda e:(e.message,e.status))
    return app.test_client()

def test_public_https_origin_behind_http_proxy(monkeypatch):
    c=client(monkeypatch)
    assert c.post('/probe',base_url='http://vaulted-sable.vercel.app',headers={'Origin':'https://vaulted-sable.vercel.app'}).status_code==200

def test_unrelated_and_insecure_origins_stay_blocked(monkeypatch):
    c=client(monkeypatch)
    for origin in ('https://evil.example','null','http://vaulted-sable.vercel.app','https://vaulted-sable.vercel.app.evil.example'):
        assert c.post('/probe',base_url='http://vaulted-sable.vercel.app',headers={'Origin':origin,'X-Forwarded-Host':'evil.example'}).status_code==403

def test_local_http_still_works(monkeypatch):
    c=client(monkeypatch,False)
    assert c.post('/probe',base_url='http://localhost:5006',headers={'Origin':'http://localhost:5006'}).status_code==200
