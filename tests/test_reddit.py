import json
from unittest.mock import Mock

import pytest
import requests

from vaulted import reddit, share_content as sc


def response(post, **overrides):
    result = Mock(status_code=200, headers={})
    data = {'id': '144ph0m', 'title': 'Long research post', 'selftext': 'Paragraph.\n'*2000,
            'is_self': True, 'author': 'writer', 'subreddit': 'research', **post}
    result.iter_content.return_value = [json.dumps([{'data': {'children': [{'kind': 't3', 'data': data}]}}]).encode()]
    for key, value in overrides.items(): setattr(result, key, value)
    return result


@pytest.mark.parametrize('url', ['https://www.reddit.com/r/research/comments/144ph0m/title/?share_id=x',
    'https://old.reddit.com/comments/144ph0m', 'https://redd.it/144ph0m',
    'https://www.reddit.com/gallery/144ph0m'])
def test_post_urls(url):
    assert reddit.post_id(url) == '144ph0m'


@pytest.mark.parametrize('url', ['https://reddit.com.evil.test/comments/144ph0m',
    'https://user:password@reddit.com/comments/144ph0m', 'https://reddit.com:444/comments/144ph0m',
    'file://reddit.com/comments/144ph0m', 'https://reddit.com/r/research/'])
def test_reject_nonposts(url):
    assert reddit.post_id(url) is None


def test_complete_text_source_and_article(monkeypatch):
    get = Mock(return_value=response({'is_self': False, 'url': 'https://example.org/article'}))
    monkeypatch.setattr(reddit.requests, 'get', get)
    monkeypatch.setattr(sc, 'fetch_web_page', lambda _: {'content': 'Complete article body'})
    note = sc.build_note({'url': 'https://redd.it/144ph0m'})
    assert ('Paragraph.\n'*2000).strip() in note['content']
    assert 'Source: https://www.reddit.com/comments/144ph0m/' in note['content']
    assert 'Article source: https://example.org/article' in note['content']
    assert 'Complete article body' in note['content']
    assert not note['warnings']
    assert get.call_args.kwargs['allow_redirects'] is False
    assert 'limit=0' in get.call_args.args[0]


def test_gallery_order_images_only(monkeypatch):
    post = {'gallery_data': {'items': [{'media_id': 'b'}, {'media_id': 'a'}, {'media_id': 'v'}]},
            'media_metadata': {'a': {'e': 'Image', 'status': 'valid', 's': {'u': 'https://i.redd.it/a.jpg'}},
                              'b': {'e': 'Image', 'status': 'valid', 's': {'u': 'https://preview.redd.it/b.jpg?a=1&amp;b=2'}},
                              'v': {'e': 'RedditVideo', 'status': 'valid', 's': {'u': 'https://v.redd.it/video.mp4'}}}}
    monkeypatch.setattr(reddit.requests, 'get', Mock(return_value=response(post)))
    result = reddit.fetch_reddit_post('https://redd.it/144ph0m')
    assert len(result['photos']) == 2
    assert 'b.jpg?a=1&b=2' in result['photos'][0]
    assert 'a.jpg' in result['photos'][1]


def test_native_shortlink_and_redirect_boundary(monkeypatch):
    redirect = Mock(status_code=302, headers={'Location': '/r/research/comments/144ph0m/title'})
    get = Mock(side_effect=[redirect, response({})])
    monkeypatch.setattr(reddit.requests, 'get', get)
    assert reddit.fetch_reddit_post('https://www.reddit.com/r/research/s/abcdXYZ')['title']
    redirect.close.assert_called_once()
    redirect.headers = {'Location': 'http://127.0.0.1/private'}
    get.side_effect = [redirect]
    get.reset_mock()
    with pytest.raises(ValueError): reddit.fetch_reddit_post('https://reddit.com/s/abcdXYZ')
    assert get.call_count == 1


def test_failure_preserves_safari_selection_and_source(monkeypatch):
    monkeypatch.setattr(sc, 'fetch_reddit_post', Mock(side_effect=requests.HTTPError()))
    note = sc.build_note({'url': 'https://reddit.com/r/research/s/abc', 'html': '<p>Selected full post</p>'})
    assert 'Selected full post' in note['content']
    assert 'Source: https://reddit.com/r/research/s/abc' in note['content']
    assert note['warnings']
    note = sc.build_note({'url': 'https://redd.it/144ph0m'})
    assert 'could not be retrieved' in note['content']


def test_video_not_imported(monkeypatch):
    monkeypatch.setattr(reddit.requests, 'get', Mock(return_value=response({'is_self': False, 'is_video': True, 'url': 'https://v.redd.it/video'})))
    note = sc.build_note({'url': 'https://redd.it/144ph0m'})
    assert 'v.redd.it' not in note['content']
    assert any('Video was not imported' in w for w in note['warnings'])


@pytest.mark.parametrize('post', [{'id': 'wrong'}, {'selftext': '[removed]'}, {'selftext': '[deleted]'}])
def test_unavailable_data_not_treated_as_full_capture(monkeypatch, post):
    monkeypatch.setattr(reddit.requests, 'get', Mock(return_value=response(post)))
    assert sc.build_note({'url': 'https://redd.it/144ph0m'})['warnings']


def test_response_limit_closes_connection(monkeypatch):
    r = response({})
    r.iter_content.return_value = [b'x' * 2_000_001]
    monkeypatch.setattr(reddit.requests, 'get', Mock(return_value=r))
    with pytest.raises(ValueError): reddit.fetch_reddit_post('https://redd.it/144ph0m')
    r.close.assert_called_once()


def test_shared_text_prefers_reddit_link():
    result = sc.normalize_payload({'text': 'See https://example.org and https://redd.it/144ph0m'})
    assert result['url'] == 'https://redd.it/144ph0m'


def test_article_failure_keeps_post(monkeypatch):
    monkeypatch.setattr(reddit.requests, 'get', Mock(return_value=response({'is_self': False, 'url': 'https://example.org/article'})))
    monkeypatch.setattr(sc, 'fetch_web_page', Mock(side_effect=OSError()))
    note = sc.build_note({'url': 'https://redd.it/144ph0m'})
    assert 'Paragraph.' in note['content']
    assert 'Article source: https://example.org/article' in note['content']
    assert len(note['warnings']) == 1


def test_inline_image_ids_become_archivable_urls(monkeypatch):
    post = {'selftext': 'Intro\n\n![img](abc123)\n\nFull conclusion',
            'media_metadata': {'abc123': {'e': 'Image', 'status': 'valid', 's': {'u': 'https://i.redd.it/abc123.jpg'}}}}
    monkeypatch.setattr(reddit.requests, 'get', Mock(return_value=response(post)))
    note = sc.build_note({'url': 'https://redd.it/144ph0m'})
    assert '![img](<https://i.redd.it/abc123.jpg>)' in note['content']
    assert 'Full conclusion' in note['content']
