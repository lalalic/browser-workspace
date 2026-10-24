"""Deterministic Stop-button and composer readiness checks (no network)."""
import json
import sys
from pathlib import Path
import subprocess
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'platforms' / 'chatgpt' / 'actions'))
from _lifecycle_common import SEND_ENABLED_JS
from chatgpt_probe import PROBE_JS


class BrowserStopGateTests(unittest.TestCase):
    def run_probe(self, *, stop=False, send_enabled=True, composer=True, body="", stop_attribute="aria-label"):
        source = r"""
const script=__SCRIPT__;
const sendScript=__SEND_SCRIPT__;
const stop=__STOP__;
const sendEnabled=__SEND__;
const composerPresent=__COMPOSER__;
const bodyText=__BODY__;
const stopAttribute=__STOP_ATTR__;
const btn={disabled:!sendEnabled,
 getAttribute:(k)=>k==='aria-disabled'?(sendEnabled?null:'true'):null,
 getClientRects:()=>[1]};
const stopBtn={
 getAttribute:(k)=>k===stopAttribute?(k==='data-testid'?'stop-button':'Stop generating'):null,
 getClientRects:()=>[1]};
const editor={innerText:'te\nst',textContent:'test',
 getAttribute:(k)=>k==='contenteditable'?'true':null,
 getClientRects:()=>[1]};
globalThis.location={pathname:'/c/test'};
globalThis.document={body:{innerText:bodyText},
 querySelectorAll:(q)=>q==='button'?(stop?[stopBtn]:[]):[btn],
 querySelector:(q)=>q.startsWith('button[')?btn:(composerPresent?editor:null)};
globalThis.getComputedStyle=()=>({visibility:'visible'});
globalThis.fetch=()=>{throw Error('network must not be called')};
const result=eval(script);
if(result.state==='READY'&&!eval(sendScript))result.state='NOT_READY';
process.stdout.write(JSON.stringify(result));
"""
        for key,val in {
          "__SCRIPT__":PROBE_JS,"__SEND_SCRIPT__":SEND_ENABLED_JS,"__STOP__":stop,"__SEND__":send_enabled,
          "__COMPOSER__":composer,"__BODY__":body,
          "__STOP_ATTR__":stop_attribute,
        }.items():
            source=source.replace(key,json.dumps(val))
        proc=subprocess.run(["node","-e",source],capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr)
        return json.loads(proc.stdout)

    def test_ready_when_stop_absent_and_composer_send_ready(self):
        state=self.run_probe()
        self.assertEqual(state["state"],"READY")
        self.assertFalse(state["stop_visible"])

    def test_lexical_layout_newline_does_not_change_exact_composer_text(self):
        state=self.run_probe()
        self.assertEqual(state["composer_text"], "test")
        self.assertIn("composer.textContent", PROBE_JS)

    def test_role_contenteditable_composer_selector(self):
        self.assertIn('[role="textbox"][contenteditable="true"]', PROBE_JS)
        self.assertEqual(self.run_probe()["state"], "READY")

    def test_visible_stop_blocks_regardless_of_send(self):
        for attr in ("aria-label","title","data-testid"):
            with self.subTest(attr=attr):
                state=self.run_probe(stop=True,stop_attribute=attr)
                self.assertEqual(state["state"],"RUNNING")
                self.assertTrue(state["stop_visible"])

    def test_disabled_send_or_missing_composer_is_not_ready(self):
        self.assertEqual(self.run_probe(send_enabled=False)["state"],"NOT_READY")
        self.assertEqual(self.run_probe(composer=False)["state"],"NOT_READY")

    def test_page_errors_are_blocked(self):
        self.assertEqual(self.run_probe(body="Could not load this ChatGPT conversation")["state"],"BLOCKED")
        self.assertEqual(self.run_probe(body="Log in to ChatGPT")["state"],"BLOCKED")


if __name__=="__main__":
    unittest.main()
