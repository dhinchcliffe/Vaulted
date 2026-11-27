import time
from unittest.mock import Mock
import pytest
from vaulted import external_images as ex, images
from vaulted.storage import VaultError

URL='https://example.org/a.png'
LOCAL='/Attachments/Web/'+'a'*64+'.png'


def test_all_common_forms_deduplicated_and_prose_links_untouched():
    text='Intro [ordinary link](https://other.org/a)\n![alt](<'+URL+'> "Title")\n![[https://example.org/a.png]]\n![ref][pic]\n[pic]: '+URL+' "Ref title"\n<img alt="A" src="'+URL+'" width="100">\nEnd.'
    assert ex.external_image_count(text)==1
    store=Mock(return_value=(LOCAL,100))
    original=images.store_remote_image
    try:
        images.store_remote_image=store
        result=ex.migrate_batch(text,Mock())
    finally: images.store_remote_image=original
    saved=result['content']
    assert 'Intro [ordinary link](https://other.org/a)' in saved and saved.endswith('End.')
    assert '[pic]: '+URL+' "Ref title"' in saved # normal reference links retain original URL
    assert '![alt]('+LOCAL+' "Title")' in saved
    assert '![['+LOCAL.lstrip('/')+']]' in saved
    assert '![ref]('+LOCAL+' "Ref title")' in saved
    assert 'src="/api/attachment'+LOCAL+'"' in saved and 'alt="A"' in saved
    assert ex.external_image_count(saved)==0 and store.call_count==1


def test_examples_comments_local_images_and_plain_links_are_not_migrated():
    content='''```markdown
![code](https://example.org/code.png)
```
Inline `![inline](https://example.org/inline.png)`
<!-- <img src="https://example.org/comment.png"> -->
    ![indented](https://example.org/indented.png)
\\![escaped](https://example.org/escaped.png)
![local](/Attachments/Web/abc.png)
![[Attachments/other.jpg]]
[link](https://example.org/page)
'''
    assert ex.external_image_count(content)==0


def test_protocol_relative_and_source_relative_images():
    content='---\nsource_url: https://source.example/page\n---\n![a](//cdn.example/a.jpg) ![b](/b.png) ![local](/Attachments/Web/local.png)'
    assert {r.url for r in ex.external_references(content)}=={'https://cdn.example/a.jpg','https://source.example/b.png'}
    assert ex.external_image_count('![relative](/images/local.png)')==0
    assert ex.external_image_count('---\nsource_url: https://[broken\n---\n![a]('+URL+')')==1


def test_html_picture_removes_remote_responsive_variants_only_on_success(monkeypatch):
    original='Before <picture><source srcset="https://img.example/big.png 2x"><img src="'+URL+'" alt="Portrait" class="photo"></picture> After'
    monkeypatch.setattr(images,'store_remote_image',Mock(return_value=(LOCAL,100)))
    result=ex.migrate_batch(original,Mock())
    assert 'source srcset' not in result['content'] and 'https://' not in result['content']
    assert result['content'].startswith('Before <picture>') and result['content'].endswith('</picture> After')
    assert 'alt="Portrait" class="photo"' in result['content']
    monkeypatch.setattr(images,'store_remote_image',Mock(side_effect=VaultError('blocked')))
    failed=ex.migrate_batch(original,Mock())
    assert failed['content']==original and failed['remaining']==1


def test_partial_failure_preserves_failed_image_and_all_prose(monkeypatch):
    text='Text ![ok]('+URL+') and ![bad](https://example.org/b.png).'
    monkeypatch.setattr(images,'store_remote_image',Mock(side_effect=[(LOCAL,100),VaultError('failed')]))
    result=ex.migrate_batch(text,Mock())
    assert result['content']=='Text ![ok]('+LOCAL+') and ![bad](https://example.org/b.png).'
    assert result['migrated']==1 and result['remaining']==1 and result['failed_urls']==['https://example.org/b.png']


def test_batches_continue_without_retrying_failed_urls(monkeypatch):
    monkeypatch.setattr(images,'MAX_IMAGES',1)
    fetch=Mock(side_effect=[VaultError('failed'),(LOCAL,100)]);monkeypatch.setattr(images,'store_remote_image',fetch)
    text='![bad]('+URL+') ![good](https://example.org/b.png)'
    first=ex.migrate_batch(text,Mock());assert first['deferred']==1 and first['failed_urls']==[URL]
    second=ex.migrate_batch(first['content'],Mock(),skip_urls=first['failed_urls'])
    assert second['migrated']==1 and second['remaining']==1 and second['deferred']==0 and fetch.call_count==2


@pytest.fixture
def authenticated_client(monkeypatch):
    import app
    from vaulted import auth
    app.app.config.update(TESTING=True,SECRET_KEY='test-only')
    vault=Mock();vault.get.return_value={'id':'note-id','content':'Note ![image]('+URL+')','revision':7,'path':'Research/note.md'}
    vault.save.return_value={'success':True,'revision':8}
    monkeypatch.setattr(auth,'SupabaseVault',Mock(return_value=vault))
    client=app.app.test_client()
    with client.session_transaction() as session:
        session['access_token']='test';session['expires_at']=time.time()+3600
    return client,vault


def test_file_load_counts_without_downloading(authenticated_client,monkeypatch):
    client,vault=authenticated_client;download=Mock();monkeypatch.setattr(images,'store_remote_image',download)
    response=client.get('/api/file?path=Research/note.md')
    assert response.json['external_image_count']==1
    assert response.json['id']=='note-id'
    download.assert_not_called();vault.store_image.assert_not_called()


def test_recent_page_loads_at_current_path(authenticated_client):
    client,vault=authenticated_client
    vault.get_by_id.return_value={**vault.get.return_value,'path':'Renamed/note.md'}
    response=client.get('/api/file?id=note-id')
    assert response.status_code==200
    assert (response.json['id'],response.json['path'])==('note-id','Renamed/note.md')
    vault.get_by_id.assert_called_once_with('note-id')
    vault.get.assert_not_called()


def test_recent_id_cannot_open_hidden_file(authenticated_client):
    client,vault=authenticated_client
    vault.get_by_id.return_value={**vault.get.return_value,'path':'.obsidian/note.md'}
    assert client.get('/api/file?id=note-id').status_code==403


def test_stale_revision_rejected_before_network(authenticated_client,monkeypatch):
    client,vault=authenticated_client;download=Mock();monkeypatch.setattr(images,'store_remote_image',download)
    response=client.post('/api/migrate-images',json={'path':'Research/note.md','revision':6},headers={'X-Vaulted-Request':'1'})
    assert response.status_code==409;download.assert_not_called();vault.save.assert_not_called()


def test_migration_uses_stored_note_and_revision_checked_save(authenticated_client,monkeypatch):
    client,vault=authenticated_client;download=Mock(return_value=(LOCAL,100));monkeypatch.setattr(images,'store_remote_image',download)
    response=client.post('/api/migrate-images',json={'path':'Research/note.md','revision':7,'url':'https://ignore.example'},headers={'X-Vaulted-Request':'1'})
    assert response.status_code==200 and response.json['revision']==8 and response.json['remaining']==0
    assert download.call_args.args[0]==URL
    vault.save.assert_called_once_with('Research/note.md','Note ![image]('+LOCAL+')',7)


def test_concurrent_edit_during_download_returns_conflict(authenticated_client,monkeypatch):
    client,vault=authenticated_client;monkeypatch.setattr(images,'store_remote_image',Mock(return_value=(LOCAL,100)))
    vault.save.side_effect=VaultError('Page changed',409)
    response=client.post('/api/migrate-images',json={'path':'Research/note.md','revision':7},headers={'X-Vaulted-Request':'1'})
    assert response.status_code==409 and 'Page changed' in response.json['error']


def test_all_failed_downloads_do_not_write_note(authenticated_client,monkeypatch):
    client,vault=authenticated_client;monkeypatch.setattr(images,'store_remote_image',Mock(side_effect=VaultError('blocked')))
    response=client.post('/api/migrate-images',json={'path':'Research/note.md','revision':7},headers={'X-Vaulted-Request':'1'})
    assert response.status_code==200 and response.json['content']==vault.get.return_value['content']
    assert response.json['revision']==7;vault.save.assert_not_called()


def test_migration_requires_login_and_csrf(authenticated_client):
    client,_=authenticated_client
    assert client.post('/api/migrate-images',json={}).status_code==403
    assert client.post('/api/migrate-images',json={},headers={'X-Vaulted-Request':'1','Origin':'https://evil.example'}).status_code==403
    with client.session_transaction() as s:s.clear()
    assert client.post('/api/migrate-images',json={},headers={'X-Vaulted-Request':'1','Authorization':'Bearer '+'a'*43}).status_code==401


def test_unclosed_fence_and_html_attribute_examples_are_ignored():
    assert ex.external_image_count('```\n![example]('+URL+')')==0
    content='<img alt="Example ![alt](https://example.org/fake.png) > text" src="'+URL+'">'
    assert {r.url for r in ex.external_references(content)}=={URL}


def test_image_inspection_does_not_change_source_text():
    note=('Paragraph with a normal link https://example.org/page.\n'*1000)+'![real]('+URL+')'
    original=note
    assert ex.external_image_count(note)==1 and note==original


def test_reference_definition_after_code_block_is_detected():
    text='```\nExample\n```\n[pic]: '+URL+'\n![a][pic]'
    assert ex.external_image_count(text)==1
