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
