"""Generate reproducible Cherri source from the audited Safari extraction script.

Compile with Cherri v2.4.0 --skip-sign --derive-uuids. Sign the PUBLIC template only;
the user's private capture token is supplied through an import question on device.
"""
import json
import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
script = json.dumps('VAULTED_SAFARI_SCRIPT')
if '--embed' in sys.argv:
    path = ROOT / 'Save-to-Vaulted.unsigned.shortcut'
    workflow = plistlib.loads(path.read_bytes())
    for action in workflow['WFWorkflowActions']:
        if action['WFWorkflowActionIdentifier'] == 'is.workflow.actions.runjavascriptonwebpage':
            action['WFWorkflowActionParameters']['WFJavaScript'] = (ROOT / 'safari-capture.js').read_text()
            action['WFWorkflowActionParameters']['WFInput'] = {'Value': {'Type': 'ExtensionInput'}, 'WFSerializationType': 'WFTextTokenAttachment'}
    token_index = next(i for i, a in enumerate(workflow['WFWorkflowActions']) if a['WFWorkflowActionParameters'].get('WFTextActionText') == 'PASTE_TOKEN_HERE')
    workflow['WFWorkflowImportQuestions'] = [{'ActionIndex': token_index, 'Category': 'Parameter', 'ParameterKey': 'WFTextActionText', 'Text': 'Paste the capture token from Vaulted → Save from iPhone', 'DefaultValue': 'PASTE_TOKEN_HERE'}]
    path.write_bytes(plistlib.dumps(workflow))
    sys.exit(0)
source = '''#include 'actions/web'
#include 'actions/crypto'
#define name Save to Vaulted
#define color blue
#define glyph folder
#define inputs webpage, url, text
#define from sharesheet
const token = text("PASTE_TOKEN_HERE")
if !ShortcutInput {
    alert("Open a Safari page or X post, tap Share, then Save to Vaulted.", "Save to Vaulted")
    stop()
}
const inputType = typeOf(ShortcutInput)
@payload = "{ShortcutInput}"
if inputType contains "Safari" {
    @payload = runJavaScriptOnWebpage(SAFARI_SCRIPT)
}
const random1 = randomNumber(0, 2147483647)
const random2 = randomNumber(0, 2147483647)
const requestSeed = text("{random1}:{random2}:{@payload}")
const requestId = hash(requestSeed, "MD5")
const response = jsonRequest("https://vaulted-sable.vercel.app/api/share/capture", "POST", {"payload": "{@payload}", "request_id": "{requestId}"}, {"Authorization": "Bearer {token}"})
const result = getDictionary(response)
const reviewURL = getValue(result, "review_url")
if reviewURL {
    openURL("{reviewURL}")
} else {
    const errorMessage = getValue(result, "error")
    alert("{errorMessage}", "Could not save to Vaulted")
}
'''.replace('SAFARI_SCRIPT', script)
(ROOT / 'save-to-vaulted.cherri').write_text(source)
