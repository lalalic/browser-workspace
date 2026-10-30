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
        if "attachmentCount" in expression:
            return {"composer": True, "text": self.text, "attachmentCount": 0}
        if "querySelectorAll('.user-message')" in expression:
            return self.messages
        raise AssertionError(f"Unexpected browser expression: {expression}")

    def fill_input(self, selector, text):
        self.text = text

    def cdp(self, method, text):
        assert method == "Input.insertText"
        self.text = text

    def click(self, selector):
        if selector == lifecycle.COMPOSER:
            return
        self.clicks += 1
        self.messages += 1
        self.text = ""
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

    result = lifecycle.run({"message": "one prompt", "timeout_seconds": 1}, "new-thread", browser.api())

    assert browser.clicks == 1
    assert result["thread_id"] == "generated-id"
    assert result["verified_by"] == "matching user message, cleared composer, and durable thread URL"


def test_new_turn_submits_once_to_requested_chat():
    browser = FakeBrowser()
    thread_id = "existing-id"
    browser.url = lifecycle.target_url(thread_id)

    result = lifecycle.run({"thread_id": thread_id, "message": "one prompt", "timeout_seconds": 1}, "new-turn", browser.api())

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