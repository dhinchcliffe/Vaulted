import pytest

pw = pytest.importorskip('playwright.sync_api')


@pytest.mark.parametrize('vault_browser', [
    {'allow_saves': True},
    {'allow_saves': True, 'viewport': {'width': 390, 'height': 844}, 'is_mobile': True, 'has_touch': True},
], ids=['desktop', 'phone'], indirect=True)
def test_rename_last_page_in_category_via_recents(vault_browser):
    page, rows, _ = vault_browser
    page.goto('http://vaulted.test/')
    pw.expect(page.locator('#editBtn')).to_be_visible()
    phone = page.locator('#browseBtn').is_visible()
    if phone:
        page.locator('#browseBtn').tap()
    page.locator('#recentPageList button').click()
    row = page.locator('#physicalTree .file.active')
    pw.expect(row).to_be_in_viewport()
    if phone:
        row.locator('.node-actions').tap()
    else:
        row.click(button='right')
    page.locator('#contextRename').click()
    pw.expect(page.locator('#renameInput')).to_have_value('Index')
    page.locator('#renameInput').fill('Field notes v2.1')
    page.locator('#confirmRenameBtn').click()
    new_path = 'One/Field notes v2.1.md'
    pw.expect(row).to_have_attribute('data-path', new_path)
    pw.expect(page.locator('#recentPageList button')).to_have_attribute('title', new_path)
    assert (rows[0]['id'], rows[0]['content'], rows[0]['revision']) == ('0', 'Original page 0', 2)
    if phone:
        page.locator('#closeDrawer').tap()
    page.locator('#editBtn').click()
    page.locator('#editor').fill('Edited after rename')
    pw.expect(page.locator('#saveStatus')).to_have_text('Saved')
    assert (rows[0]['content'], rows[0]['revision']) == ('Edited after rename', 3)
    # Existing clients can have an extensionless last-file preference from a broken rename.
    page.evaluate("localStorage.setItem('vaulted_lastFile', 'One/Field notes v2.1')")
    page.reload()
    pw.expect(page.locator('#preview')).to_have_text('Edited after rename')


def test_rename_suffix_noop_collision_and_directory(vault_browser):
    page, rows, _ = vault_browser
    rows[1]['path'] = 'Archive.md/Index.md'
    page.goto('http://vaulted.test/')
    pw.expect(page.locator('#editBtn')).to_be_visible()
    def rename(path, name):
        return page.evaluate("""async ([path,new_name]) => {
            const r = await fetch('/api/rename', {method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({path,new_name})});
            return [r.status, await r.json()];
        }""", [path, name])

    status, result = rename('One/Index.md', 'Index')
    assert status == 200 and result['count'] == 0 and rows[0]['revision'] == 1
    status, result = rename('One/Index.md', 'Renamed.MD')
    assert status == 200 and result['new_path'] == 'One/Renamed.md'
    status, result = rename('Archive.md', 'Records')
    assert status == 200 and rows[1]['path'] == 'Records/Index.md'
    rows.append(dict(id='other',path='One/Existing.md',content='Keep me',revision=1))
    assert rename('One/Renamed.md', 'Existing')[0] == 409
    assert rows[0]['path'] == 'One/Renamed.md' and rows[-1]['content'] == 'Keep me'


@pytest.mark.parametrize('vault_browser', [{'allow_saves': True}], indirect=True)
def test_rename_does_not_adopt_an_unseen_edit(vault_browser):
    page, rows, _ = vault_browser
    page.goto('http://vaulted.test/')
    pw.expect(page.locator('#editBtn')).to_be_visible()
    page.locator('#recentPageList button').click()
    row = page.locator('#physicalTree .file.active')
    pw.expect(row).to_be_in_viewport()
    rows[0].update(content='Concurrent edit', revision=2)
    row.click(button='right')
    page.locator('#contextRename').click()
    page.locator('#renameInput').fill('Changed')
    page.locator('#confirmRenameBtn').click()
    pw.expect(row).to_have_attribute('data-path','One/Changed.md')
    page.locator('#editBtn').click()
    page.locator('#editor').fill('Local draft')
    pw.expect(page.locator('#saveStatus')).to_contain_text('Save conflict')
    pw.expect(page.locator('#editor')).to_have_value('Local draft')
    assert (rows[0]['content'], rows[0]['revision']) == ('Concurrent edit', 3)
