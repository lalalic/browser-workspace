import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "actions"
_spec = importlib.util.spec_from_file_location("z_lifecycle_common", ACTIONS / "_lifecycle_common.py")
lifecycle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lifecycle)


class FakeBrowser:
    def __init__(self, url="https://example.com/"):
        self.url = url
        self.text = ""
        self.messages = 0
        self.clicks = 0
        self.stream_body = None
        self.stream_count = 0
        self.submission = None
        self.prompt = None

    def api(self):
        return {name: getattr(self, name) for name in (
            "page_info", "goto_url", "wait_for_load", "wait_for_element",
            "js", "fill_input", "click", "cdp",
        )}

    def page_info(self):
        return {"url": self.url}

    def goto_url(self, url):
        self.url = url

    def wait_for_load(self):
        pass

    def wait_for_element(self, selector, **kwargs):
        return True

    def js(self, expression):
        if "observer.submission = " in expression:
            import re
            m = re.search(r'baseline: (\d+), message: (".*")', expression)
            assert m
            import json
            self.submission = {"baseline": int(m.group(1)), "message": json.loads(m.group(2))}
            return None
        if "const marker = o?.submission" in expression:
            return {"baseline": self.submission["baseline"],
                    "currentCount": self.stream_count,
                    "valid": self.messages > 0} if self.submission else None
        if "window.__webhelmZStream?.version === 1" in expression:
            return None
        if "__webhelmZStream?.entries.at" in expression:
            return self.stream_body or ""
        if "__webhelmZStream?.entries" in expression:
            return {"count": self.stream_count, "latest": {
                "state": "received", "status": 200, "error": ""
            } if self.stream_count else None}
        if "attachmentCount" in expression:
            return {"composer": True, "text": self.text, "attachmentCount": 0}
        if "querySelectorAll('.user-message')" in expression:
            return self.messages
        raise AssertionError(f"Unexpected browser expression: {expression}")

    def fill_input(self, selector, text):
        self.text = text

    def cdp(self, method, text=None, source=None):
        if method == "Page.addScriptToEvaluateOnNewDocument":
            assert source and "__webhelmZStream" in source
        else:
            assert method == "Input.insertText"
            self.text = text

    def click(self, selector):
        if selector == lifecycle.COMPOSER:
            return
        self.clicks += 1
        self.messages += 1
        self.text = ""
        if self.stream_body is not None:
            self.stream_count = 1
        if self.url == lifecycle.BASE_URL:
            self.url = lifecycle.BASE_URL + "c/generated-id"


def test_manifest_and_actions_exist():
    manifest = (ROOT / "manifest.yaml").read_text(encoding="utf-8")
    assert "new-thread: actions/_new_thread.py" in manifest
    assert "new-turn: actions/_new_turn.py" in manifest
    assert (ACTIONS / "_new_thread.py").is_file()
    assert (ACTIONS / "_new_turn.py").is_file()


def test_thread_id_requires_z_ai_chat_route():
    assert lifecycle.thread_id_from_url("https://chat.z.ai/c/abc-123") == "abc-123"
    assert lifecycle.thread_id_from_url("https://chat.z.ai/") is None
    assert lifecycle.thread_id_from_url("https://other.example/c/abc-123") is None
    assert lifecycle.target_url("abc 123") == "https://chat.z.ai/c/abc%20123"


def test_new_thread_submits_once_and_returns_durable_id():
    browser = FakeBrowser()

    result = lifecycle.run({"message": "one prompt", "timeout_seconds": 1, "wait": False}, "new-thread", browser.api())

    assert browser.clicks == 1
    assert result["thread_id"] == "generated-id"
    assert result["status"] == "submitted"
    assert result["verified_by"].startswith("matching user message")


def test_new_turn_submits_once_to_requested_chat():
    browser = FakeBrowser()
    thread_id = "existing-id"
    browser.url = lifecycle.target_url(thread_id)

    result = lifecycle.run({"thread_id": thread_id, "message": "one prompt", "timeout_seconds": 1, "wait": False}, "new-turn", browser.api())

    assert browser.clicks == 1
    assert result["thread_id"] == thread_id
    assert result["thread_url"] == lifecycle.target_url(thread_id)


def test_new_turn_rejects_redirect_before_submission():
    browser = FakeBrowser()
    browser.goto_url = lambda url: setattr(browser, "url", "https://chat.z.ai/c/other-id")

    with pytest.raises(RuntimeError, match="redirect mismatch"):
        lifecycle.run({"thread_id": "expected-id", "message": "one prompt"}, "new-turn", browser.api())

    assert browser.clicks == 0


def test_new_thread_preserves_existing_draft():
    browser = FakeBrowser("https://chat.z.ai/c/existing-id")
    browser.text = "keep this draft"

    with pytest.raises(RuntimeError, match="Unsent draft"):
        lifecycle.run({"message": "one prompt"}, "new-thread", browser.api())

    assert browser.url == "https://chat.z.ai/c/existing-id"
    assert browser.clicks == 0
def sse(*chunks):
    import json
    return "\n\n".join("data: " + json.dumps(item) for item in chunks) + "\n\n"


def test_sse_is_not_complete_until_explicit_done_and_answer():
    delta = {"type": "chat:completion", "data": {"delta_content": "final text"}}
    end = {"type": "chat:completion", "data": {"done": True}}
    assert lifecycle.parse_site_stream(sse(delta)) is None
    assert lifecycle.parse_site_stream(sse(end)) is None
    assert lifecycle.parse_site_stream(sse(delta, end)) == "final text"
    assert lifecycle.parse_site_stream(sse(delta, {"type": "status", "data": {"done": True}})) is None


def test_sse_reconstructs_chunks_and_does_not_return_thinking_or_tools():
    data = [
        {"type": "chat:completion", "data": {"phase": "thinking", "delta_content": "private reasoning"}},
        {"type": "chat:completion", "data": {"phase": "other", "delta_content": "Z"}},
        {"type": "chat:completion", "data": {"phase": "other", "delta_content": " response"}},
        {"type": "chat:completion", "data": {"phase": "tool_response", "delta_content": "tool secret"}},
        {"type": "chat:completion", "data": {"phase": "done", "done": True}}
    ]
    assert lifecycle.parse_site_stream(sse(*data)) == "Z response"
    with pytest.raises(RuntimeError, match="error event"):
        lifecycle.parse_site_stream(sse({"type": "error", "data": {"code": 429}}))


def test_new_thread_completes_from_same_session_sse_once():
    b = FakeBrowser()
    b.stream_body = sse({"type": "chat:completion", "data": {"delta_content": "Test marker"}},
                        {"type": "chat:completion", "data": {"done": True}})
    out = lifecycle.run({"message": "please reply", "timeout_seconds": 1}, "new-thread", b.api())
    assert out["status"] == "completed"
    assert out["answer"] == "Test marker"
    assert b.clicks == 1


def test_new_turn_json_and_resume_does_not_resubmit():
    b = FakeBrowser(lifecycle.target_url('existing-id'))
    b.stream_body = sse({"type": "chat:completion", "data": {"content": '{"ok":true}'}},
                        {"type": "chat:completion", "data": {"done": True}})
    out = lifecycle.run({"thread_id": "existing-id", "message": "reply in JSON",
                         "response_format": "json", "timeout_seconds": 1}, "new-turn", b.api())
    assert out["status"] == "completed"
    assert out["data"] == {"ok": True}
    count = b.clicks
    resumed = lifecycle.run({"resume": True, "thread_id": "existing-id",
                             "timeout_seconds": 1}, "new-turn", b.api())
    assert resumed["status"] == "completed"
    assert b.clicks == count


def test_resume_without_stream_fails_closed_and_keeps_draft():
    b = FakeBrowser(lifecycle.target_url("existing"))
    result = lifecycle.run({"resume": True, "thread_id": "existing"}, "new-turn", b.api())
    assert result["status"] == "pending"
    assert b.clicks == 0

def test_resume_rejects_stale_unrelated_stream_in_same_tab():
    b = FakeBrowser(lifecycle.target_url("existing"))
    b.stream_body = sse({"type": "chat:completion", "data": {"content": "OLD"}},
                        {"type": "chat:completion", "data": {"done": True}})
    b.stream_count = 1
    result = lifecycle.run({"resume": True, "thread_id": "existing"}, "new-turn", b.api())
    assert result["status"] == "pending"
    assert b.clicks == 0
