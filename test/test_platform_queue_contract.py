import json

import platform_runner


def test_new_turn_is_persisted_via_daemon_without_browser_session(monkeypatch, tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"project_id": "p", "thread_id": "t", "message": "hello", "idempotency_key": "key-1"}))
    calls = []

    def fake_request(payload):
        calls.append(payload)
        return {"ok": True, "status": "queued", "queue_id": "msg-1", "thread_id": "t"}

    monkeypatch.setattr(platform_runner, "request", fake_request)
    result = platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))
    assert result["session_mode"] == "durable_queue"
    assert result["result"]["queue_id"] == "msg-1"
    assert calls == [{"op": "chatgpt-new-turn-enqueue", "thread_id": "t", "project_id": "p",
                      "message": "hello", "idempotency_key": "key-1"}]
