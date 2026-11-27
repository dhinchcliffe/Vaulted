"""Browser fixture using the real UI and a synthetic Flask test vault."""
import os
import shutil
import time
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest

from app import app
from vaulted import auth
from vaulted.storage import VaultError


@pytest.fixture
def vault_browser(monkeypatch, request):
    pw = pytest.importorskip('playwright.sync_api')
    chromium = os.environ.get('CHROMIUM_EXECUTABLE_PATH') or shutil.which('chromium')
    if not chromium:
        pytest.skip('System Chromium is required for browser tests')

    names = ['One/Index.md', 'Two/Index.md'] + [f'Page {i}.md' for i in range(101)]
    rows = [dict(id=str(i), path=name, content=f'Original page {i}', revision=1) for i, name in enumerate(names)]
    def lookup(field, value):
        for row in rows:
            if row[field] == value:
                return row
        raise VaultError('File not found', 404)

    vault = Mock()
    vault.rows.side_effect = lambda: rows
    vault.get.side_effect = lambda path: lookup('path', path)
    vault.get_by_id.side_effect = lambda file_id: lookup('id', file_id)
    def create(path, content):
        rows.append(dict(id=str(len(rows)), path=path, content=content, revision=1))
    def move(source, destination):
        lookup('path', source)['path'] = destination
        return {'success': True, 'new_path': destination}
    vault.create.side_effect = create
    vault.move.side_effect = move
    vault.call.return_value.json.return_value = [{'path': rows[0]['path']}]
    vault.search.return_value = [dict(path='Two/Index.md', preview='A match', matches=1)]
    vault.save.side_effect = VaultError('Save conflict', 409)
    monkeypatch.setattr(auth, 'SupabaseVault', lambda token: vault)
    monkeypatch.setitem(app.config, 'SECRET_KEY', 'test-only')
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(access_token='test', expires_at=time.time() + 3600)

    requests = []
    def serve(route):
        req = route.request
        url = urlsplit(req.url)
        assert url.hostname == 'vaulted.test'
        target = url.path + ('?' + url.query if url.query else '')
        requests.append((req.method, target))
        response = client.open(target, method=req.method, data=req.post_data,
                               headers={'X-Vaulted-Request': '1', 'Content-Type': 'application/json'})
        route.fulfill(status=response.status_code, content_type=response.content_type, body=response.data)

    with pw.sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium)
        context = browser.new_context(**getattr(request, 'param', {}))
        context.route('**/*', serve)
        page = context.new_page()
        yield page, rows, requests
        browser.close()
