import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import requests
from vaulted import translation as tr, share_content as sc

SPANISH = 'Los investigadores han descubierto un nuevo método para almacenar energía. Es una noticia importante.'
ENGLISH = 'Researchers have discovered a new way to store energy. This is important news.'


def fake_result(translated=True, text=ENGLISH, finish='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(refusal=None,
        content=json.dumps({'needs_translation':translated,'source_language':'Spanish' if translated else 'English','english_text':text})))])


def test_english_posts_skip_all_translation_calls(monkeypatch):
    ai=Mock();fx=Mock();monkeypatch.setattr(tr,'ai_translate',ai)
    assert tr.translate_x_text('English post','en',fx)==(None,None)
    ai.assert_not_called();fx.assert_not_called()


def test_public_translation_requires_complete_original_and_english(monkeypatch):
    ai=Mock();monkeypatch.setattr(tr,'ai_translate',ai)
    result,warning=tr.translate_x_text(SPANISH,'es',lambda:{'text':SPANISH,'translation':{'text':ENGLISH,'source_lang':'es','target_lang':'en'}})
    assert result['text']==ENGLISH and result['provider']=='FxTwitter' and not warning
    ai.assert_not_called()


@pytest.mark.parametrize('post',[
 {'text':'Short excerpt','translation':{'text':ENGLISH,'source_lang':'es','target_lang':'en'}},
 {'text':SPANISH,'translation':{'text':ENGLISH,'source_lang':'es','target_lang':'fr'}},
 {'text':SPANISH,'translation':{'text':'Short','source_lang':'es','target_lang':'en'}},
 {'text':SPANISH,'translation':None},
])
def test_unusable_public_translation_falls_back(monkeypatch,post):
    ai=Mock(return_value={'text':ENGLISH,'language':'Spanish','provider':'Vaulted AI'});monkeypatch.setattr(tr,'ai_translate',ai)
    result,warning=tr.translate_x_text(SPANISH,'es',lambda:post)
    assert result['provider']=='Vaulted AI' and not warning;ai.assert_called_once_with(SPANISH)


def test_timeout_never_loses_original(monkeypatch):
    monkeypatch.setattr(sc,'fetch_x_post',Mock(return_value={'text':SPANISH,'photos':[],'author':'Author','lang':'es'}))
    monkeypatch.setattr(tr,'ai_translate',Mock(side_effect=TimeoutError()))
    note=sc.build_note({'url':'https://x.com/a/status/1234567890'})
    assert SPANISH in note['content'] and 'translation was unavailable' in note['content']
    assert note['warnings'] and '## English translation' not in note['content']


def test_translation_first_original_photos_source_and_english_title_retained(monkeypatch):
    post={'text':SPANISH,'photos':['![Photo](https://pbs.twimg.com/media/a.jpg)'],'author':'Author','lang':'es'}
    monkeypatch.setattr(sc,'fetch_x_post',Mock(return_value=post))
    monkeypatch.setattr(sc,'translate_x_text',Mock(return_value=({'text':ENGLISH,'language':'Spanish','provider':'Vaulted AI'},None)))
    note=sc.build_note({'url':'https://x.com/a/status/1234567890'})
    assert note['title'].startswith('Author — Researchers')
    assert note['content'].index('## English translation')<note['content'].index('## Original captured content')
    assert SPANISH in note['content'] and 'https://pbs.twimg.com/media/a.jpg' in note['content']
    assert 'Source: https://x.com/i/status/1234567890' in note['content']


def test_regular_web_pages_never_translate(monkeypatch):
    translate=Mock();monkeypatch.setattr(sc,'translate_x_text',translate)
    sc.build_note({'url':'https://example.org/page','html':'<p>'+SPANISH+'</p>'})
    translate.assert_not_called()


def test_translation_output_cannot_embed_model_images():
    from vaulted.images import image_links
    text='![invented](https://evil.example/image.png) <img src="https://evil.example/a">'
    output=tr.plain_markdown(text)
    assert not list(image_links(output)) and '<img' not in output


def test_full_ai_translation_and_english_detection(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','test-only');client=Mock();client.chat.completions.create.return_value=fake_result()
    monkeypatch.setattr(tr,'OpenAI',Mock(return_value=client))
    assert tr.ai_translate(SPANISH)['text']==ENGLISH
    client.close.assert_called_once()
    client.chat.completions.create.return_value=fake_result(False,'')
    assert tr.ai_translate('Hello world') is None


def test_long_post_translation_is_chunked_without_slicing_original(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','test-only');client=Mock();monkeypatch.setattr(tr,'OpenAI',Mock(return_value=client))
    source=(SPANISH+'\n')*150
    parts=list(tr.chunks(source));assert ''.join(parts)==source and len(parts)>1
    client.chat.completions.create.side_effect=[fake_result(text='Translated sentence. '*400) for _ in parts]
    result=tr.ai_translate(source)
    assert client.chat.completions.create.call_count==len(parts) and result['text'].count('Translated sentence.')==400*len(parts)


def test_partial_or_truncated_ai_translation_is_never_presented(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','test-only');client=Mock();monkeypatch.setattr(tr,'OpenAI',Mock(return_value=client))
    client.chat.completions.create.side_effect=[fake_result(text='Translated sentence. '*400),fake_result(finish='length')]
    with pytest.raises(ValueError,match='Incomplete translation'):tr.ai_translate((SPANISH+'\n')*100)
    client.close.assert_called_once()


def test_size_limit_keeps_original_when_translation_wont_fit(monkeypatch):
    monkeypatch.setattr(sc,'MAX_TEXT',200)
    monkeypatch.setattr(sc,'fetch_x_post',Mock(return_value={'text':SPANISH,'photos':[],'author':'Author','lang':'es'}))
    monkeypatch.setattr(sc,'translate_x_text',Mock(return_value=({'text':ENGLISH,'language':'Spanish','provider':'Vaulted AI'},None)))
    note=sc.build_note({'url':'https://x.com/a/status/1234567890'})
    assert SPANISH in note['content'] and 'size limit' in note['content'] and '## English translation' not in note['content']
