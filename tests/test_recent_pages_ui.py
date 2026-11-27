"""Exercise the real navigation UI against synthetic notes, with optional Playwright/Chromium."""
import pytest

pw = pytest.importorskip('playwright.sync_api')


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
    pw.expect(page.locator('#physicalTree .active')).to_be_in_viewport()
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
    pw.expect(page.locator('#physicalTree .active')).to_have_attribute('data-path', 'Moved/Renamed.md')


@pytest.mark.parametrize('vault_browser', [
    {'viewport': {'width': 1440, 'height': 900}},
    {'viewport': {'width': 834, 'height': 1194}, 'has_touch': True, 'is_mobile': True},
    {'viewport': {'width': 390, 'height': 844}, 'has_touch': True, 'is_mobile': True},
], ids=['desktop', 'ipad', 'phone'], indirect=True)
def test_recent_selection_reveals_physical_row(vault_browser):
    page, rows, requests = vault_browser
    rows[1]['path'] = 'Two/Field notes/Index.md'
    page.add_init_script("""localStorage.setItem('vaulted_recentPageIds',
        JSON.stringify(Array.from({length: 100}, (_, index) => String(index))))""")
    page.goto('http://vaulted.test/')
    pw.expect(page.locator('#editBtn')).to_be_visible()
    if page.locator('#browseBtn').is_visible():
        page.locator('#browseBtn').tap()
    original = page.locator('#physicalTree .file[data-path="Two/Field notes/Index.md"]')
    pw.expect(original).to_be_hidden()
    alias = page.locator('#recentPageList [data-recent-id="1"]')
    requests.clear()
    if page.evaluate('navigator.maxTouchPoints'):
        alias.tap()
    else:
        alias.click()
    pw.expect(page.locator('#physicalTree .active')).to_have_attribute('data-path', rows[1]['path'])
    pw.expect(original).to_be_in_viewport()
    pw.expect(original).to_be_focused()
    pw.expect(page.locator('#physicalTree .directory.expanded')).to_have_count(2)
    assert requests == [('GET', '/api/file?id=1')]
    if page.locator('#closeDrawer').is_visible():
        page.locator('#closeDrawer').tap()
    pw.expect(page.locator('#preview')).to_have_text('Original page 1')


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
