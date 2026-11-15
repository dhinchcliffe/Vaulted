"""Supabase Auth sessions in secure, HttpOnly cookies; membership enforced by RLS."""
import os,time
from datetime import timedelta
import requests
from flask import Blueprint,session,request,redirect,render_template,jsonify,g
from .storage import VaultError,SupabaseVault
bp=Blueprint('auth',__name__)
def auth_call(path,payload=None,token=None,method='POST'):
    h={'apikey':os.environ['SUPABASE_PUBLISHABLE_KEY']}
    if token:h['Authorization']='Bearer '+token
    r=requests.request(method,os.environ['SUPABASE_URL']+'/auth/v1/'+path,headers=h,json=payload,timeout=20)
    if not r.ok:raise VaultError('Sign-in failed. Check your email and password.',401)
    return r.json() if r.content else {}
def set_session(data):
    session['access_token']=data['access_token'];session['refresh_token']=data['refresh_token']
    session['expires_at']=time.time()+data.get('expires_in',3600)
    session.permanent=True

def install_auth(app):
    app.secret_key=os.environ.get('SESSION_SECRET')
    app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SECURE=bool(os.environ.get('VERCEL')),SESSION_COOKIE_SAMESITE='Strict',PERMANENT_SESSION_LIFETIME=timedelta(hours=96),MAX_CONTENT_LENGTH=4*1024*1024)
    app.register_blueprint(bp)
    @app.before_request
    def protect():
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('Origin')
            if origin and origin.rstrip('/')!=request.host_url.rstrip('/'):raise VaultError('Cross-site request rejected',403)
            if request.path.startswith('/api/') and request.headers.get('X-Vaulted-Request')!='1':raise VaultError('Missing request protection',403)
        if request.endpoint in ('auth.login','static','health'):return
        if not session.get('access_token'):
            if request.path.startswith('/api/'):raise VaultError('Please sign in again',401)
            return redirect('/login')
        if session.get('expires_at',0)<time.time()+60:
            try:set_session(auth_call('token?grant_type=refresh_token',{'refresh_token':session['refresh_token']}))
            except VaultError:
                session.clear();raise
        auth_call('user',token=session['access_token'],method='GET')
        g.vault=SupabaseVault(session['access_token'])
        if not g.vault.call('GET','/rest/v1/vault_members',params={'select':'user_id','limit':1}).json():raise VaultError('This account does not have access to this vault',403)

@bp.route('/login',methods=['GET','POST'])
def login():
    error=None
    if request.method=='POST':
        try:
            data=auth_call('token?grant_type=password',{'email':request.form.get('email','').strip(),'password':request.form.get('password','')})
            v=SupabaseVault(data['access_token'])
            if not v.call('GET','/rest/v1/vault_members',params={'select':'user_id','limit':1}).json():raise VaultError('Account not authorized',403)
            session.clear();set_session(data);return redirect('/')
        except VaultError as e:error=e.message
    return render_template('login.html',error=error)
@bp.post('/logout')
def logout():
    try:auth_call('logout',token=session.get('access_token'))
    finally:session.clear()
    return redirect('/login')
@bp.route('/account',methods=['GET','POST'])
def account():
    message=None
    if request.method=='POST':
        password=request.form.get('password','')
        if len(password)<12:message='Use at least 12 characters.'
        else:
            auth_call('user',{'password':password},session['access_token'],method='PUT')
            message='Password updated.'
    return render_template('account.html',message=message)
