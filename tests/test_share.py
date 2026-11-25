import json
import uuid
from unittest.mock import Mock

import pytest
import requests
from vaulted import share_content as sc
from vaulted.storage import VaultError


def test_normalize_safari_json_and_source():
    assert sc.normalize_payload({'payload': json.dumps({'url': 'https://example.org/page', 'html': '<p>Page</p>'})})['url'] == 'https://example.org/page'
    assert sc.normalize_payload({'payload': 'Interesting: https://x.com/someone/status/1234567890?s=46'})['url'].startswith('https://x.com/')


@pytest.mark.parametrize('value', [{'url': 'file:///etc/passwd'}, {'url': 'https://user:pass@example.org'}, {'text': []}, {'html': 'x'*1000001}, {}])
def test_invalid_capture(value):
    with pytest.raises(VaultError): sc.normalize_payload(value)


def test_long_x_text_and_still_images(monkeypatch):
    long_text = 'Long post paragraph.\n' * 1200
    monkeypatch.setattr(sc, 'fetch_x_post', lambda _: {'text': long_text, 'photos': ['![photo](https://pbs.twimg.com/media/example.jpg)'], 'author': 'Author'})
    note = sc.build_note({'url': 'https://x.com/author/status/1234567890?s=46'})
    assert long_text.strip() in note['content']
    assert 'Source: https://x.com/i/status/1234567890' in note['content']
    assert 'example.jpg' in note['content']
    assert not note['warnings']


def test_x_unavailable_keeps_link_and_shared_text(monkeypatch):
    def fail(_): raise requests.Timeout()
    monkeypatch.setattr(sc, 'fetch_x_post', fail)
    note = sc.build_note({'url': 'https://x.com/a/status/1234567890', 'text': 'Text provided by the user'})
    assert 'Text provided by the user' in note['content']
    assert 'https://x.com/i/status/1234567890' in note['content']
    assert note['warnings']


def test_link_only_failure_is_explicit(monkeypatch):
    monkeypatch.setattr(sc, 'fetch_x_post', Mock(side_effect=ValueError()))
    note = sc.build_note({'url': 'https://x.com/a/status/1234567890'})
    assert 'could not be retrieved' in note['content']
    assert note['warnings']


def test_safari_content_not_replaced_by_shorter_x_excerpt(monkeypatch):
    monkeypatch.setattr(sc, 'fetch_x_post', lambda _: {'text': 'Truncated', 'photos': [], 'author': 'Author'})
    note = sc.build_note({'url': 'https://x.com/a/status/1234567890', 'html': '<p>' + 'Long content ' * 100 + '</p>'})
    assert 'Long content ' * 99 in note['content']


def test_html_keeps_absolute_images_and_links_without_video():
    body = sc.clean_html('<p>Hello</p><img src="/photo.jpg"><a href="/story">Story</a><video src="/movie.mp4"></video><iframe src="https://evil.example"></iframe><img src="data:secret">', 'https://example.org/page')
    assert 'https://example.org/photo.jpg' in body
    assert 'https://example.org/story' in body
    for excluded in ('movie.mp4', 'evil.example', 'data:secret'): assert excluded not in body


def test_x_api_uses_full_text_and_only_still_photos(monkeypatch):
    data = {'code': 200, 'tweet': {'id': '1234567890', 'text': 'short', 'raw_text': {'text': 'full text '*100}, 'media': {'photos': [{'url': 'https://pbs.twimg.com/media/photo.jpg', 'type': 'photo'}, {'url': 'https://evil.example/a.jpg'}, {'url': 'https://pbs.twimg.com/a.gif', 'type': 'gif'}], 'videos': [{'url': 'https://video.twimg.com/video.mp4'}]}}}
    response = Mock()
    response.iter_content.return_value = [json.dumps(data).encode()]
    monkeypatch.setattr(sc.requests, 'get', Mock(return_value=response))
    result = sc.fetch_x_post('1234567890')
    assert len(result['text']) > 800
    assert len(result['photos']) == 1
    assert 'photo.jpg' in result['photos'][0]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('SESSION_SECRET', 'tests-only')
    import app
    app.app.config.update(TESTING=True, SECRET_KEY='tests-only')
    return app.app.test_client()


def test_capture_missing_token_is_denied(client):
    assert client.post('/api/share/capture', json={'payload': 'Note'}).status_code == 401


def test_auth_checked_before_remote_fetch(client, monkeypatch):
    from vaulted import sharing
    monkeypatch.setattr(sharing, 'capture_rpc', Mock(side_effect=VaultError('Invalid token', 401)))
    build = Mock()
    monkeypatch.setattr(sharing, 'build_note', build)
    r = client.post('/api/share/capture', json={'payload': 'https://example.org/'}, headers={'Authorization': 'Bearer bad'})
    assert r.status_code == 401
    build.assert_not_called()


def test_capture_returns_authenticated_review_without_ai(client, monkeypatch):
    from vaulted import sharing
    file_id = str(uuid.uuid4())
    rpc = Mock(side_effect=[{'file_id': None}, {'file_id': file_id}])
    monkeypatch.setattr(sharing, 'capture_rpc', rpc)
    r = client.post('/api/share/capture', json={'payload': 'Test note', 'request_id': str(uuid.uuid4())}, headers={'Authorization': 'Bearer ' + 'a'*43})
    assert r.status_code == 200
    assert r.json['review_url'].endswith('/share/review/' + file_id)
    assert rpc.call_args_list[1].args[0] == 'vault_share_finish'
    review = client.get('/share/review/' + file_id)
    assert review.status_code == 302 and 'next=' in review.location


def test_capture_retry_does_not_fetch_or_save_twice(client, monkeypatch):
    from vaulted import sharing
    monkeypatch.setattr(sharing, 'capture_rpc', Mock(return_value={'file_id': str(uuid.uuid4())}))
    build = Mock()
    monkeypatch.setattr(sharing, 'build_note', build)
    r = client.post('/api/share/capture', json={'payload': 'Note'}, headers={'Authorization': 'Bearer ' + 'a'*43})
    assert r.status_code == 200
    build.assert_not_called()


def test_capture_token_does_not_authorize_existing_apis(client):
    for path in ('/api/file', '/api/move-file', '/api/share/token', '/api/share/revoke'):
        r = client.post(path, json={}, headers={'Authorization': 'Bearer ' + 'a'*43, 'X-Vaulted-Request': '1'})
        assert r.status_code == 401


def test_review_path_is_escaped(client, monkeypatch):
    from vaulted import auth
    import time
    vault = Mock()
    vault.call.return_value.json.return_value = [{'path': 'Inbox/" onload="alert(1).md'}]
    monkeypatch.setattr(auth, 'SupabaseVault', Mock(return_value=vault))
    with client.session_transaction() as s:
        s['access_token'] = 'test'; s['expires_at'] = time.time()+1000
    r = client.get('/share/review/' + str(uuid.uuid4()))
    assert r.status_code == 200
    assert 'data-capture-path="Inbox/&#34;' in r.text


@pytest.mark.parametrize('next_path', ['https://evil.example', '//evil.example', '/\\evil.example'])
def test_login_rejects_external_review_redirect(client, monkeypatch, next_path):
    from vaulted import auth
    monkeypatch.setattr(auth, 'auth_call', Mock(return_value={'access_token': 'test', 'refresh_token': 'test'}))
    vault = Mock(); vault.call.return_value.json.return_value = [{'user_id': 'test'}]
    monkeypatch.setattr(auth, 'SupabaseVault', Mock(return_value=vault))
    with client.session_transaction() as s: s['csrf_token'] = 'csrf'
    r = client.post('/login', query_string={'next': next_path}, data={'csrf_token': 'csrf'})
    assert r.status_code == 302 and r.location == '/'
