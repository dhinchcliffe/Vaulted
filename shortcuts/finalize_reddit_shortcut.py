"""Finalize the credential-free Cherri v2.4.0 test workflow before signing."""
from pathlib import Path
import plistlib
import uuid

ROOT = Path(__file__).resolve().parent
source = ROOT / 'Reddit to Vaulted Test_unsigned.shortcut'
workflow = plistlib.loads(source.read_bytes())
workflow['WFWorkflowName'] = 'Reddit to Vaulted Test'
# Cherri's deterministic UUID mode reuses a control-flow group for sequential
# conditionals. Give each block its own stable group for an unambiguous import.
stack = []
for index, action in enumerate(workflow['WFWorkflowActions']):
    parameters = action.get('WFWorkflowActionParameters', {})
    if action['WFWorkflowActionIdentifier'] == 'is.workflow.actions.conditional':
        mode = parameters['WFControlFlowMode']
        if mode == 0:
            stack.append(str(uuid.uuid5(uuid.NAMESPACE_URL, f'vaulted-reddit-test-if-{index}')))
        parameters['GroupingIdentifier'] = stack[-1]
        if mode == 2:
            parameters['UUID'] = stack.pop()
assert not stack
index = next(i for i, a in enumerate(workflow['WFWorkflowActions'])
             if a.get('WFWorkflowActionParameters', {}).get('WFTextActionText') == 'PASTE_TOKEN_HERE')
workflow['WFWorkflowImportQuestions'] = [{'ActionIndex': index, 'Category': 'Parameter',
    'ParameterKey': 'WFTextActionText', 'Text': 'Paste a capture token from Vaulted → Save from iPhone',
    'DefaultValue': 'PASTE_TOKEN_HERE'}]
(ROOT / 'Reddit-to-Vaulted-Test.unsigned.shortcut').write_bytes(plistlib.dumps(workflow))
source.unlink()
