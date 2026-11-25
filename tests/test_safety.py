import pytest
from vaulted.storage import valid_path,VaultError,build_tree
from vaulted.capture import safe_fetch
@pytest.mark.parametrize('path',['../secret','/etc/passwd','a/../../x','a\\b','a/../b','.obsidian/config'])
def test_invalid_paths(path):
    with pytest.raises(VaultError):valid_path(path)
def test_tree_is_portable():
    tree=build_tree([{'path':'Z.md'},{'path':'A/B.md'},{'path':'.obsidian/config.json'}])
    assert tree[0]['children'][0]['path']=='A/B.md'
    assert len(tree)==2
@pytest.mark.parametrize('url',['http://127.0.0.1/','http://169.254.169.254/','file:///etc/passwd','http://localhost/','https://example.com:8443/'])
def test_capture_blocks_private_and_non_web(url):
    with pytest.raises(VaultError):safe_fetch(url)
