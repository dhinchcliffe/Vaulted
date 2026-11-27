"""Touch navigation on the shared editor, including a held finger and a scrolling gesture."""
import pytest

pw = pytest.importorskip('playwright.sync_api')
pytestmark = pytest.mark.parametrize('vault_browser', [{
    'viewport': {'width': 390, 'height': 844}, 'has_touch': True, 'is_mobile': True
}], indirect=True)


def open_phone(page):
    page.goto('http://vaulted.test/')
    pw.expect(page.locator('#editBtn')).to_be_visible()
    pw.expect(page.locator('#currentFile')).to_have_text('Index.md')


def test_phone_toolbar_search_rotation_and_override(vault_browser):
    page, _, _ = vault_browser
    open_phone(page)
    for width, height in [(320, 568), (430, 932), (932, 430)]:
        page.set_viewport_size(dict(width=width, height=height))
        for selector in ('#browseBtn', '#editBtn', '#moreBtn', '.content'):
            bounds = page.locator(selector).bounding_box()
            assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
        pw.expect(page.locator('#vaultSidebar')).to_be_hidden()
        page.locator('#moreBtn').tap()
        for selector in ('#quickPasteBtn', '#addWebBtn', '#autoFileBtn', '#useFull'):
            pw.expect(page.locator(selector)).to_be_in_viewport()
        page.locator('#moreBtn').tap()

    page.locator('#moreBtn').tap()
    page.locator('#quickPasteBtn').tap()
    pw.expect(page.locator('#quickPasteModal')).to_be_visible()
    page.locator('#quickPasteModal .modal-close').tap()
    page.locator('#browseBtn').tap()
    page.locator('#drawerSearch').tap()
    page.locator('#searchInput').fill('match')
    page.locator('.search-result-item').tap()
    pw.expect(page.locator('#preview')).to_have_text('Original page 1')
    pw.expect(page.locator('#vaultSidebar')).to_be_hidden()

    page.locator('#moreBtn').tap()
    page.locator('#useFull').tap()
    pw.expect(page.locator('#currentFile')).to_have_text('Two/Index.md')
    page.reload()
    pw.expect(page.locator('#restorePhone')).to_be_in_viewport()
    page.locator('#restorePhone').tap()
    pw.expect(page.locator('#browseBtn')).to_be_visible()
    page.set_viewport_size(dict(width=834, height=1194))
    pw.expect(page.locator('#browseBtn')).to_be_hidden()
    pw.expect(page.locator('#vaultSidebar')).to_be_visible()
    pw.expect(page.locator('#currentFile')).to_have_text('Two/Index.md')


def test_drawer_keeps_reading_position_and_dirty_editor(vault_browser):
    page, rows, _ = vault_browser
    rows[0]['content'] = '\n\n'.join(['A paragraph for scrolling.'] * 150)
    open_phone(page)
    scroll = page.locator('.editor-container')
    scroll.evaluate('el => {el.scrollTop = 600}')
    page.locator('#browseBtn').tap()
    page.locator('#closeDrawer').tap()
    assert scroll.evaluate('el => el.scrollTop') == 600
    page.locator('#editBtn').tap()
    page.locator('#editor').fill('Unsaved draft')
    page.locator('#browseBtn').tap()
    page.locator('.file[data-path="Page 0.md"]').tap()
    pw.expect(page.locator('#drawerStatus')).to_contain_text('Save conflict')
    pw.expect(page.locator('#vaultSidebar')).to_be_visible()
    page.locator('#drawerBackdrop').tap(position={'x': 380, 'y': 250})
    pw.expect(page.locator('#editor')).to_have_value('Unsaved draft')
    pw.expect(page.locator('#previewBtn')).to_be_in_viewport()


def test_touch_node_actions_hold_and_scroll(vault_browser):
    page, _, requests = vault_browser
    open_phone(page)
    page.locator('#browseBtn').tap()
    folder = page.locator('.directory[data-path="Two"]')
    folder.get_by_role('button', name='Actions for Two').tap()
    pw.expect(page.locator('#contextAddPage')).to_be_in_viewport()
    page.locator('#contextAddPage').tap()
    pw.expect(page.locator('#addPageModal')).to_be_visible()
    page.locator('#addPageModal .modal-close').tap()
    pw.expect(folder).to_have_class('tree-item directory collapsed')
    folder.tap(position={'x': 34, 'y': 20})
    row = page.locator('.file[data-path="Two/Index.md"]')
    row.scroll_into_view_if_needed()
    bounds = row.bounding_box()
    x, y = bounds['x'] + 48, bounds['y'] + 22
    cdp = page.context.new_cdp_session(page)
    def touch(kind, points):
        cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': points})

    requests.clear()
    touch('touchStart', [{'x': x, 'y': y}])
    pw.expect(page.locator('#contextRename')).to_be_visible()
    touch('touchEnd', [])
    pw.expect(page.locator('#contextRename')).to_be_visible()
    pw.expect(page.locator('#contextAddPage')).to_be_hidden()
    assert page.evaluate('String(getSelection())') == ''
    assert not any('/api/file?' in path for _, path in requests)
    page.locator('#contextRename').tap()
    pw.expect(page.locator('#renameInput')).to_have_value('Index.md')
    page.locator('#renameModal .modal-close').tap()

    touch('touchStart', [{'x': x, 'y': y}])
    touch('touchMove', [{'x': x, 'y': y - 30}])
    page.wait_for_timeout(600)
    touch('touchEnd', [])
    pw.expect(page.locator('#contextMenu')).to_be_hidden()
    pw.expect(page.locator('#vaultSidebar')).to_be_visible()
    row.tap(position={'x': 48, 'y': 22})
    pw.expect(page.locator('#preview')).to_have_text('Original page 1')
    pw.expect(page.locator('#vaultSidebar')).to_be_hidden()


def test_folder_add_and_file_rename_target_real_nodes(vault_browser):
    page, rows, _ = vault_browser
    open_phone(page)
    page.locator('#browseBtn').tap()
    page.get_by_role('button', name='Actions for Two', exact=True).tap()
    page.locator('#contextAddPage').tap()
    page.locator('#addPageInput').fill('Field notes')
    page.locator('#confirmAddPageBtn').tap()
    pw.expect(page.locator('#currentFile')).to_have_text('Field notes.md')
    pw.expect(page.locator('#vaultSidebar')).to_be_hidden()
    page.locator('#browseBtn').tap()
    page.get_by_role('button', name='Actions for Two/Field notes.md', exact=True).tap()
    page.locator('#contextRename').tap()
    page.locator('#renameInput').fill('Renamed.md')
    page.locator('#confirmRenameBtn').tap()
    pw.expect(page.get_by_role('button', name='Actions for Two/Renamed.md')).to_be_visible()
    page.locator('#closeDrawer').tap()
    pw.expect(page.locator('#currentFile')).to_have_text('Renamed.md')
    assert rows[-1]['path'] == 'Two/Renamed.md'


def test_phone_share_review_keeps_autofile_and_vault_link(vault_browser):
    page, _, _ = vault_browser
    page.route('**/api/suggest-file-location', lambda route: route.fulfill(
        json={'suggestion': 'Research', 'reasoning': 'Synthetic review'}))
    page.set_viewport_size({'width': 320, 'height': 568})
    page.goto('http://vaulted.test/share/review/00000000-0000-0000-0000-000000000001')
    pw.expect(page.locator('#confirmFileBtn')).to_be_in_viewport()
    page.locator('#autoFileModal .modal-close').tap()
    pw.expect(page.locator('.capture-back')).to_be_in_viewport()
    pw.expect(page.locator('#moreBtn')).to_be_in_viewport()
    page.locator('#browseBtn').tap()
    pw.expect(page.locator('#recentPages')).to_be_visible()
