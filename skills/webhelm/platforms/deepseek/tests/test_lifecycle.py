import importlib.util
from pathlib import Path

import pytest

ACTION = Path(__file__).resolve().parents[1] / "actions/_lifecycle_common.py"
SPEC = importlib.util.spec_from_file_location("deepseek_lifecycle", ACTION)
lifecycle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lifecycle)
THREAD = "68155317-aece-4988-83b0-e0881d33064a"


def test_thread_url_requires_deepseek_and_canonical_uuid():
    assert lifecycle.thread_id_from_url("https://chat.deepseek.com/a/chat/s/" + THREAD) == THREAD
    assert lifecycle.thread_id_from_url("https://example.com/a/chat/s/" + THREAD) is None
    assert lifecycle.thread_id_from_url("https://chat.deepseek.com/a/chat/s/../bad") is None


def test_new_turn_rejects_missing_thread_before_navigation():
    with pytest.raises(ValueError, match="canonical UUID"):
        lifecycle.run({"message": "hello"}, "new-turn", {})


def test_rejects_unknown_response_format():
    with pytest.raises(ValueError, match="response_format"):
        lifecycle.run({"message": "hello", "response_format": "xml"}, "new-thread", {})


def test_busy_draft_is_preserved():
    browser = {
        "page_info": lambda: {"url": "https://chat.deepseek.com/"},
        "wait_for_element": lambda *args, **kwargs: None,
        "js": lambda expression: {"draft": True, "idle": False},
    }
    with pytest.raises(RuntimeError, match="leave it untouched"):
        lifecycle.run({"message": "hello"}, "new-thread", browser)


def fake_browser(state, answer="Paris"):
    def click(selector):
        state["clicked"] += 1
        state["url"] = "https://chat.deepseek.com/a/chat/s/" + THREAD

    def js(expression):
        if expression == lifecycle.ANSWER_STATE:
            # One answer existed before submit; a new one appears after polling once.
            ready = state["clicked"] and state["answer_polls"] > 0
            state["answer_polls"] += bool(state["clicked"])
            return {"count": 2 if ready else 1, "answer": answer if ready else "old", "settled": True}
        if "input[type=file]" in expression:
            return ".png,.jpg"
        if "image.naturalWidth" in expression:
            return True
        if "draft:" in expression:
            state["idle_checks"] += 1
            return {"draft": False, "idle": state["idle_checks"] > 1}
        if ".ds-message" in expression:
            return state["clicked"]
        return True

    def wait(seconds):
        state["waits"].append((state["clicked"], seconds))

    return {
        "page_info": lambda: {"url": state["url"]},
        "goto_url": lambda url: state.update(url=url),
        "wait_for_load": lambda: None, "wait_for_element": lambda *args, **kwargs: None,
        "fill_input": lambda *args: None, "click": click, "js": js, "wait": wait,
        "upload_file": lambda selector, path: state["uploads"].append(path),
    }


def new_state():
    return {"url": "https://example.com/", "clicked": 0, "idle_checks": 0,
            "answer_polls": 0, "waits": [], "uploads": []}


@pytest.mark.parametrize("mode", ["new-thread", "new-turn"])
@pytest.mark.parametrize("with_image", [False, True])
def test_submits_once_and_returns_new_answer(mode, with_image, tmp_path):
    state = new_state()
    cfg = {"message": "hello", "thread_id": THREAD}
    if with_image:
        image = tmp_path / "image.png"
        image.write_bytes(b"test")
        cfg["image"] = str(image)
    result = lifecycle.run(cfg, mode, fake_browser(state))
    assert result["status"] == "completed"
    assert result["answer"] == "Paris"
    assert result["thread_id"] == THREAD
    assert state["clicked"] == 1
    assert len(state["uploads"]) == int(with_image)


def test_wait_false_returns_submission_receipt():
    state = new_state()
    result = lifecycle.run({"message": "hello", "wait": False}, "new-thread", fake_browser(state))
    assert result["status"] == "submitted"
    assert "answer" not in result
    assert state["answer_polls"] == 0


def test_json_response_is_parsed_from_fenced_block():
    state = new_state()
    browser = fake_browser(state, answer='Here:\n```json\n{"city": "Paris"}\n```')
    result = lifecycle.run({"message": "hello", "response_format": "json"}, "new-thread", browser)
    assert result["data"] == {"city": "Paris"}
    assert "parse_error" not in result


def test_invalid_json_response_keeps_text_and_reports_error():
    state = new_state()
    result = lifecycle.run({"message": "hello", "response_format": "json"}, "new-thread", fake_browser(state))
    assert result["data"] is None
    assert result["answer"] == "Paris"
    assert result["parse_error"]


def test_timeout_returns_pending_without_resubmitting(monkeypatch):
    browser = {"js": lambda expression: {"count": 1, "answer": "", "settled": False},
               "wait": lambda seconds: None}
    clock = iter([0, 0, 5])
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: next(clock))
    result = lifecycle.wait_for_answer(browser, {"thread_id": THREAD}, {}, 1, 1)
    assert result["status"] == "pending"
    assert "resume=true" in result["next_step"]


def test_resume_reads_without_submitting():
    browser = {
        "page_info": lambda: {"url": "https://chat.deepseek.com/a/chat/s/" + THREAD},
        "js": lambda expression: {"count": 3, "answer": "done", "settled": True},
        "wait": lambda seconds: None,
    }
    result = lifecycle.run({"resume": True}, "new-turn", browser)
    assert result["status"] == "completed"
    assert result["answer"] == "done"
    assert result["verified_by"] == "resumed without resubmitting"


def test_new_turn_rejects_redirect_without_submission():
    browser = {
        "page_info": lambda: {"url": "https://chat.deepseek.com/"},
        "goto_url": lambda url: None, "wait_for_load": lambda: None,
        "wait_for_element": lambda *args, **kwargs: None,
        "js": lambda expression: {"draft": False, "idle": True},
    }
    with pytest.raises(RuntimeError, match="redirect mismatch"):
        lifecycle.run({"message": "hello", "thread_id": THREAD}, "new-turn", browser)
