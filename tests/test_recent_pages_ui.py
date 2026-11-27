"""Exercise the real navigation UI against synthetic notes, with optional Playwright/Chromium."""
import os
import shutil
import time
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest

from app import app
from vaulted import auth
from vaulted.storage import VaultError

pw = pytest.importorskip('playwright.sync_api')


@pytest.fixture
def vault_browser(monkeypatch):
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
        context = browser.new_context()
        context.route('**/*', serve)
        page = context.new_page()
        yield page, rows, requests
        browser.close()


def test_recent_pages_follow_original_and_preserve_editor(vault_browser):
    page, rows, requests = vault_browser
    page.goto('http://vaulted.test/')
    recent = page.locator('#recentPageList button')
    pw.expect(recent).to_have_count(1)
    page.locator('.directory[data-path="Two"]').click()
    requests.clear()
    page.locator('.file[data-path="Two/Index.md"]').click()
    pw.expect(recent.first).to_have_attribute('title', 'Two/Index.md')
    assert requests == [('GET', '/api/file?path=Two%2FIndex.md')]
    pw.expect(recent.nth(1)).to_contain_text('One/Index.md')

    # A different page has since taken over the old path.
    rows[0]['path'] = 'Moved/Renamed.md'
    rows.append(dict(id='other', path='One/Index.md', content='Different page', revision=1))
    recent.nth(1).click()
    pw.expect(page.locator('#preview')).to_have_text('Original page 0')
    pw.expect(recent.first).to_have_attribute('title', 'Moved/Renamed.md')
    pw.expect(page.locator('#physicalTree .active')).to_have_attribute('data-path', 'Moved/Renamed.md')
    pw.expect(recent).to_have_count(2)

    heading = page.locator('#recentPages > summary')
    heading.focus()
    heading.press('Enter')
    pw.expect(recent.first).to_be_hidden()
    page.reload()
    pw.expect(page.locator('#currentFile')).to_have_text('Moved/Renamed.md')
    pw.expect(recent.first).to_be_hidden()
    heading.click()
    pw.expect(recent).to_have_count(2)

    page.locator('#editBtn').click()
    page.locator('#editor').fill('Unsaved edit')
    recent.nth(1).click()
    pw.expect(page.locator('#saveStatus')).to_contain_text('Save conflict')
    pw.expect(page.locator('#editor')).to_have_value('Unsaved edit')
    pw.expect(recent.first).to_have_attribute('aria-current', 'page')


def test_recent_limit_and_missing_page(vault_browser):
    page, rows, _ = vault_browser
    page.goto('http://vaulted.test/')
    recent = page.locator('#recentPageList button')
    pw.expect(recent).to_have_count(1)
    for row in rows[2:]:
        page.locator(f'.file[data-path="{row["path"]}"]').click()
        pw.expect(recent.first).to_have_attribute('title', row['path'])
    pw.expect(recent).to_have_count(100)
    page.reload()
    pw.expect(recent).to_have_count(100)
    pw.expect(recent.first).to_have_attribute('title', 'Page 100.md')
    pw.expect(recent.last).to_have_attribute('title', 'Page 1.md')
    removed = rows.pop(-2)
    recent.nth(1).click()
    pw.expect(recent).to_have_count(99)
    assert removed['path'] not in recent.evaluate_all('(items) => items.map(item => item.title)')
    pw.expect(page.locator('#currentFile')).to_have_text('Page 100.md')


def test_search_open_with_browser_storage_unavailable(vault_browser):
    page, _, _ = vault_browser
    page.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new Error('Disabled')}})")
    page.goto('http://vaulted.test/')
    recent = page.locator('#recentPageList button')
    pw.expect(recent).to_have_count(1)
    page.locator('#searchBtn').click()
    pw.expect(page.locator('#recentPages')).to_be_hidden()
    page.locator('#searchInput').fill('match')
    page.locator('.search-result-item').click()
    pw.expect(page.locator('#currentFile')).to_have_text('Two/Index.md')
    page.locator('#searchCloseBtn').click()
    pw.expect(recent.first).to_have_attribute('title', 'Two/Index.md')
    pw.expect(recent).to_have_count(2)
