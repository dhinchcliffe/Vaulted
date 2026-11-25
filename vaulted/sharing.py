"""Capture-only capabilities are distinct from authenticated browsing and filing."""
import os
import secrets
import uuid
from flask import Blueprint, request, jsonify, g, render_template, current_app
from .storage import SupabaseVault, VaultError
from .share_content import normalize_payload, build_note
from .images import archive_images

bp = Blueprint('sharing', __name__)
PUBLIC_ORIGIN = 'https://vaulted-sable.vercel.app'


def capture_rpc(name, **params):
    vault = SupabaseVault('')
    vault.headers.pop('Authorization', None)
    return vault.call('POST', '/rest/v1/rpc/' + name, json=params).json()


@bp.get('/share/setup')
def setup():
    tokens = g.vault.call('POST', '/rest/v1/rpc/vault_share_tokens', json={}).json()
    return render_template('share_setup.html', tokens=tokens)


@bp.post('/api/share/token')
def create_token():
    # The raw token is returned once. Only its SHA-256 digest is persisted.
    token = secrets.token_urlsafe(32)
    import hashlib
    result = g.vault.call('POST', '/rest/v1/rpc/vault_share_create_token',
                          json={'p_hash': hashlib.sha256(token.encode()).hexdigest()}).json()
    return jsonify(token=token, id=result['id'])


@bp.post('/api/share/revoke')
def revoke_token():
    try:
        token_id = str(uuid.UUID(request.get_json().get('id', '')))
    except (ValueError, TypeError, AttributeError):
        raise VaultError('Invalid shortcut token')
    g.vault.call('POST', '/rest/v1/rpc/vault_share_revoke', json={'p_id': token_id})
    return jsonify(success=True)


@bp.post('/api/share/capture')
def capture():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer ') or len(auth) > 200:
        raise VaultError('Set up your Save to Vaulted shortcut token first.', 401)
    token = auth[7:]
    data = request.get_json(silent=True)
    payload = normalize_payload(data)
    try:
        request_id = str(uuid.UUID(data.get('request_id', ''))) if data.get('request_id') else str(uuid.uuid4())
    except (ValueError, TypeError, AttributeError):
        raise VaultError('Invalid capture request ID')
    # Authenticate and reserve quota BEFORE doing any network capture work.
    claim = capture_rpc('vault_share_claim', p_token=token, p_request=request_id)
    warnings = []
    if claim.get('file_id'):
        result = claim
    else:
        note = build_note(payload)
        note['content'], image_warnings = archive_images(note['content'], lambda data, mime:
            capture_rpc('vault_share_image', p_token=token, p_request=request_id, p_data=data, p_mime=mime))
        warnings = note['warnings'] + image_warnings
        result = capture_rpc('vault_share_finish', p_token=token, p_request=request_id,
                             p_title=note['title'], p_content=note['content'])
    current_app.logger.info('share_capture saved request=%s file=%s warnings=%d', request_id, result['file_id'], len(warnings))
    return jsonify(success=True, review_url=PUBLIC_ORIGIN + '/share/review/' + result['file_id'], warnings=warnings)


@bp.get('/share/review/<uuid:file_id>')
def review(file_id):
    # Browsing still requires the ordinary user session and RLS membership.
    rows = g.vault.call('GET', '/rest/v1/vault_files',
                        params={'id': 'eq.' + str(file_id), 'select': 'path', 'limit': 1}).json()
    if not rows:
        raise VaultError('This captured note was not found.', 404)
    return render_template('index.html', capture_path=rows[0]['path'])
