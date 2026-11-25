import base64
from unittest.mock import Mock
import pytest
from vaulted import images
from vaulted.storage import VaultError, SupabaseVault

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXXsAAAAASUVORK5CYII=')
PATH = 'Attachments/Web/' + 'a'*64 + '.png'


def test_archive_duplicates_keeps_alt_title_and_prose(monkeypatch):
    fetch = Mock(return_value=(PNG, 'https://example.org/a(1).png'))
    store = Mock(return_value={'path': PATH})
    monkeypatch.setattr(images, 'safe_fetch', fetch)
    original = '# Text\n\n![An image](<https://example.org/a(1).png> "Title")\n![Again](https://example.org/a\\(1\\).png)\nKeep this.'
    saved, warnings = images.archive_images(original, store)
    assert saved == '# Text\n\n![An image](/'+PATH+' "Title")\n![Again](/'+PATH+')\nKeep this.'
    assert not warnings
    fetch.assert_called_once();store.assert_called_once_with(base64.b64encode(PNG).decode(), 'image/png')


def test_failed_image_becomes_explicit_link_not_remote_embed(monkeypatch):
    monkeypatch.setattr(images, 'safe_fetch', Mock(side_effect=VaultError('blocked')))
    saved, warnings = images.archive_images('![Picture](https://example.org/private.png)', Mock())
    assert '![Picture]' not in saved and '[Image not archived' in saved
    assert 'https://example.org/private.png' in saved and warnings


def test_reject_svg_or_html_disguised_as_image(monkeypatch):
    monkeypatch.setattr(images, 'safe_fetch', Mock(return_value=(b'<svg onload="alert(1)">', 'https://example.org/a.png')))
    store=Mock();saved,warnings=images.archive_images('![](https://example.org/a.png)',store)
    store.assert_not_called();assert warnings and '![]' not in saved


def test_local_images_are_not_downloaded(monkeypatch):
    fetch=Mock();monkeypatch.setattr(images,'safe_fetch',fetch)
    original='![Alt](/'+PATH+') ![[Attachments/older.png]]'
    assert images.archive_images(original,Mock()) == (original,[])
    fetch.assert_not_called()


def test_image_limit_preserves_text_and_marks_remaining(monkeypatch):
    monkeypatch.setattr(images,'MAX_IMAGES',1)
    monkeypatch.setattr(images,'safe_fetch',Mock(return_value=(PNG,'')))
    saved,warnings=images.archive_images('Text ![](https://a.example/1.png) ![](https://a.example/2.png)',Mock(return_value={'path':PATH}))
    assert saved.startswith('Text ![](/Attachments/Web/') and len(warnings)==1
    assert '[Image not archived' in saved


def test_capture_images_reuse_public_ip_validation(monkeypatch):
    from vaulted import capture
    monkeypatch.setattr(capture.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    connect=Mock();monkeypatch.setattr(capture.socket,'create_connection',connect)
    with pytest.raises(VaultError,match='Private network'):capture.safe_fetch('https://example.org/image',image=True)
    connect.assert_not_called()


def test_private_bytes_download_does_not_use_external_storage(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL','https://example.supabase.co');monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY','test')
    vault=SupabaseVault('test');vault.call=Mock()
    vault.call.return_value.json.return_value={'data':base64.b64encode(PNG).decode()}
    assert vault.download({'id':'image-id','object_key':None})==PNG
    vault.call.assert_called_once_with('POST','/rest/v1/rpc/vault_read_image',json={'p_id':'image-id'})


def test_shared_image_saved_before_note_and_retry_skips(monkeypatch):
    import app,time
    from vaulted import sharing
    app.app.config.update(TESTING=True,SECRET_KEY='tests-only')
    rpc=Mock(side_effect=[{'file_id':None},{'path':PATH},{'file_id':'12345678-1234-1234-1234-123456789abc'}])
    monkeypatch.setattr(sharing,'capture_rpc',rpc)
    monkeypatch.setattr(images,'safe_fetch',Mock(return_value=(PNG,'')))
    with app.app.test_client() as client:
        r=client.post('/api/share/capture',json={'url':'https://example.org/page','html':'<p>Text</p><img src="/a.png">'},headers={'Authorization':'Bearer '+'a'*43})
        assert r.status_code==200
        assert rpc.call_args_list[1].args[0]=='vault_share_image'
        assert '/'+PATH in rpc.call_args_list[2].kwargs['p_content']
        assert client.get('/api/attachment?path='+PATH).status_code==401
