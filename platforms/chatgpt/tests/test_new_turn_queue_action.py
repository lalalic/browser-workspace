import contextlib
import io
import json
import sys
import types
from pathlib import Path


ACTION = Path(__file__).parents[1] / "actions" / "_new_turn.py"


def run_action(monkeypatch, *, url=None, loading=False, composer=True, stop=False, error=False):
    cfg = {"thread_id": "thread-123", "project_id": "project-1", "message": "continue"}
    config_path = ACTION.parent / "test-config.json"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    submitted = []
    fake = types.ModuleType("_lifecycle_common")
    fake.target_url = lambda **kw: "https://chatgpt.com/g/project-1/c/thread-123?prompt=continue"
    fake.raise_if_visible_delivery_error = lambda: (_ for _ in ()).throw(RuntimeError("ChatGPT load error")) if error == "known" else None
    def submit(message, *, before_click=None):
        if before_click:
            before_click()
        submitted.append(message)
        return {"verified_by": "send-button-disabled", "turn": {"id": "turn-1"}}
    fake.prefilled_submit = submit
    monkeypatch.setitem(sys.modules, "_lifecycle_common", fake)
    namespace = {
        "js": lambda expression: loading if "document.readyState" in expression else
            error is True if "[role=" in expression else
            composer if "#prompt-textarea" in expression else stop,
        "goto_url": lambda _url: None,
        "wait_for_load": lambda: None,
        "page_info": lambda: {"url": url or "https://chatgpt.com/g/project-1/c/thread-123"},
    }
    source = ACTION.read_text(encoding="utf-8").replace('"__CFG_PATH__"', repr(str(config_path)))
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            exec(compile(source, str(ACTION), "exec"), namespace)
    finally:
        config_path.unlink(missing_ok=True)
    return json.loads(output.getvalue()), submitted


def test_verified_idle_thread_submits_and_visible_stop_button_only_defers(monkeypatch):
    idle, idle_submitted = run_action(monkeypatch)
    assert idle["status"] == "submitted"
    assert idle_submitted == ["continue"]
    busy, busy_submitted = run_action(monkeypatch, stop=True)
    assert busy["status"] == "busy"
    assert busy_submitted == []


def test_loading_wrong_thread_and_visible_error_fail_closed(monkeypatch):
    for kwargs, expected in [
        ({"loading": True}, "still loading"),
        ({"url": "https://chatgpt.com/c/other-thread"}, "redirect mismatch"),
        ({"composer": False}, "ambiguous"),
        ({"error": "known"}, "ChatGPT load error"),
        ({"error": True}, "visible error"),
    ]:
        try:
            run_action(monkeypatch, **kwargs)
        except RuntimeError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("expected fail-closed new-turn action")

