import json
import pytest
from vaulted.filing import existing_folders,resolve_folder,folder_choices,parse_suggestion
from vaulted.storage import VaultError

PARENT='Personal Research/Ancient History'
CLEAN=PARENT+'/Persian History'
SPACED=PARENT+'/ Persian History'

def test_existing_folders_include_ancestors_and_hide_metadata():
    assert existing_folders([{'path':CLEAN+'/note.md'},{'path':'.obsidian/x.json'}])==['Personal Research',PARENT,CLEAN]

def test_whitespace_case_and_new_child_reuse_existing_spelling():
    assert resolve_folder(PARENT+'/ Persian history ',[CLEAN])==CLEAN
    assert resolve_folder(CLEAN,[SPACED])==SPACED
    assert resolve_folder(CLEAN+'/New topic',[SPACED])==SPACED+'/New topic'

def test_equivalent_choices_prefer_clean_folder():
    assert list(folder_choices([SPACED,CLEAN]).values())==[CLEAN]

@pytest.mark.parametrize('target',[CLEAN+' REASONING: because',CLEAN+'\nBecause',CLEAN+'/note.md','a/../b','a//b'])
def test_bad_destinations_are_rejected(target):
    with pytest.raises(VaultError):resolve_folder(target,[CLEAN])

def test_explanation_cannot_enter_destination():
    choices={'folder_0':CLEAN}
    result=parse_suggestion(json.dumps({'folder_id':'folder_0','reasoning':'REASONING: This note discusses Persian History.'}),choices)
    assert result['suggestion']==CLEAN
    assert result['reasoning'].startswith('REASONING:')

@pytest.mark.parametrize('output',['SUGGESTION: x REASONING: y','{"folder_id":"folder_0 REASONING: y","reasoning":"y"}','{"folder_id":"missing","reasoning":"y"}','{"folder_id":true,"reasoning":"y"}','{"folder_id":"folder_0","reasoning":null}','[]'])
def test_invalid_model_output_is_not_a_path(output):
    with pytest.raises(VaultError):parse_suggestion(output,{'folder_0':CLEAN})
