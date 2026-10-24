import json
import tomllib
from pathlib import Path

import platform_runner


def test_new_turn_is_persisted_via_daemon_without_browser_session(monkeypatch, tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"project_id": "p", "thread_id": "t", "message": "hello", "idempotency_key": "key-1"}))
    calls = []

    def fake_request(payload):
        calls.append(payload)
        return {"ok": True, "status": "queued", "queue_id": "msg-1", "thread_id": "t", "state": "WAITING"}

    monkeypatch.setattr(platform_runner, "request", fake_request)
    result = platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))
    assert result["session_mode"] == "durable_queue"
    assert result["result"] == {
        "ok": True, "status": "submitted", "mode": "new-turn", "project_id": "p",
        "thread_id": "t", "thread_url": "https://chatgpt.com/g/p/c/t",
        "verified_by": "durable-queue", "user_message_id": None,
        "queue_id": "msg-1", "state": "WAITING",
    }
    assert calls == [{"op": "chatgpt-new-turn-enqueue", "thread_id": "t", "project_id": "p",
                      "message": "hello", "idempotency_key": "key-1"}]


def test_new_turn_rejects_invalid_queue_receipt(monkeypatch, tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "expected", "message": "hello"}))
    monkeypatch.setattr(platform_runner, "request", lambda _: {
        "ok": True, "status": "queued", "queue_id": "msg-1", "thread_id": "wrong"})
    import pytest
    with pytest.raises(ValueError, match="invalid acceptance receipt"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))


def test_distribution_versions_match_daemon_version_source():
    root = Path(__file__).resolve().parents[1]
    versions = [
        json.loads((root / "package.json").read_text())["version"],
        json.loads((root / "src/browser_workspace_app/package.json").read_text())["version"],
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"],
        tomllib.loads((root / "src/browser_workspace_app/pyproject.toml").read_text())["project"]["version"],
    ]
    assert len(set(versions)) == 1, versions


def test_new_turn_sync_uses_caller_session_without_private_session(monkeypatch, tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello", "sync": True}))
    calls = []
    def fake_request(payload):
        calls.append(payload)
        return {"ok": True, "stdout": json.dumps({"status": "submitted", "mode": "new-turn", "thread_id": "t", "verified_by": "user-turn", "user_message_id": "m1"}) + "\n"}
    monkeypatch.setattr(platform_runner, "request", fake_request)
    result = platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config), session_id="existing")
    assert result["session_mode"] == "caller_owned_self_heal_capable"
    assert result["result"]["status"] == "submitted"
    assert result["result"]["user_message_id"] == "m1"
    assert result["result"]["cleanup"] == {"caller_owned_session": True}
    assert len(calls) == 1 and calls[0]["op"] == "exec" and calls[0]["session_id"] == "existing"


def test_new_turn_sync_invalid_receipts_and_arguments(monkeypatch, tmp_path):
    import pytest
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello"}))
    with pytest.raises(ValueError, match="requires caller-owned"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config), sync=True)
    with pytest.raises(ValueError, match="does not accept browser session"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config), session_id="existing")
    monkeypatch.setattr(platform_runner, "request", lambda _: {"ok": True, "stdout": json.dumps({"status": "queued", "thread_id": "t"})})
    with pytest.raises(ValueError, match="invalid submission receipt"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config), session_id="existing", sync=True)
    config.write_text(json.dumps({"thread_id": "t", "message": "hello", "sync": "true"}))
    with pytest.raises(ValueError, match="must be a boolean"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))


def test_new_turn_queue_rejects_unknown_success_status(monkeypatch, tmp_path):
    import pytest
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello"}))
    monkeypatch.setattr(platform_runner, "request", lambda _: {"ok": True, "status": "submitted"})
    with pytest.raises(ValueError, match="invalid acceptance receipt"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))
