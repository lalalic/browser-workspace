import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import platform_runner
import chatgpt_delivery_errors


@pytest.fixture(autouse=True)
def fixture_chatgpt_platform(tmp_path, monkeypatch):
    root = tmp_path / "platforms"
    actions = root / "chatgpt" / "actions"
    actions.mkdir(parents=True)
    (root / "chatgpt" / "manifest.yaml").write_text("actions:\n  new-turn: actions/_new_turn.py\n")
    (actions / "_new_turn.py").write_text("print('{}')\n")
    monkeypatch.setattr(platform_runner, "PLATFORMS", root)


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
                      "message": "hello", "mergeable": False, "idempotency_key": "key-1"}]


def test_new_turn_rejects_invalid_queue_receipt(monkeypatch, tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "expected", "message": "hello"}))
    monkeypatch.setattr(platform_runner, "request", lambda _: {
        "ok": True, "status": "queued", "queue_id": "msg-1", "thread_id": "wrong"})
    import pytest
    with pytest.raises(ValueError, match="invalid acceptance receipt"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))


def test_new_turn_preserves_queue_delivery_error(monkeypatch, tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello"}))
    monkeypatch.setattr(chatgpt_delivery_errors, "LOG", tmp_path / "errors.jsonl")
    monkeypatch.setattr(platform_runner, "request", lambda _: {"ok": False, "error": "queue unavailable"})
    result = platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))
    assert result["result"]["ok"] is False
    assert result["result"]["code"] == "delivery_failed"
    assert "error" not in result["result"]
    assert result["result"].get("status") != "submitted"


def test_sync_new_turn_uses_caller_session_and_keeps_submitted_status(monkeypatch, tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"project_id": "p", "thread_id": "t", "message": "hello", "mode": "sync"}))
    calls = []

    def fake_request(payload):
        calls.append(payload)
        return {"ok": True, "stdout": json.dumps({
            "status": "submitted", "mode": "new-turn", "project_id": "p", "thread_id": "t",
            "thread_url": "https://chatgpt.com/g/p/c/t", "verified_by": "send-button",
            "user_message_id": "message-1",
        })}

    monkeypatch.setattr(platform_runner, "request", fake_request)
    result = platform_runner.run_platform_action(
        "chatgpt", "new-turn", config_path=str(config), session_id="caller-session", mode="sync"
    )
    assert result["session_mode"] == "caller_owned_self_heal_capable"
    assert result["result"]["status"] == "submitted"
    assert result["result"]["mode"] == "new-turn"
    assert result["result"]["project_id"] == "p"
    assert result["result"]["thread_url"] == "https://chatgpt.com/g/p/c/t"
    assert result["result"]["verified_by"] == "send-button"
    assert result["result"]["user_message_id"] == "message-1"
    assert [call["op"] for call in calls] == ["exec"]
    assert calls[0]["session_id"] == "caller-session"


def test_sync_new_turn_rejects_invalid_submission_receipt(monkeypatch, tmp_path):
    import pytest

    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello", "mode": "sync"}))
    monkeypatch.setattr(platform_runner, "request", lambda _: {"ok": True, "stdout": '{"status":"queued"}'})
    with pytest.raises(ValueError, match="invalid submission receipt"):
        platform_runner.run_platform_action(
            "chatgpt", "new-turn", config_path=str(config), session_id="caller-session"
        )


def test_sync_new_turn_rejects_wrong_thread_or_unverified_receipt(monkeypatch, tmp_path):
    import pytest

    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "target", "message": "hello", "mode": "sync"}))
    for receipt in (
        {"status": "submitted", "mode": "new-turn", "thread_id": "another", "verified_by": "send-button"},
        {"status": "submitted", "mode": "new-turn", "thread_id": "target"},
        {"status": "submitted", "mode": "unexpected", "thread_id": "target", "verified_by": "send-button"},
    ):
        monkeypatch.setattr(platform_runner, "request",
                            lambda _, receipt=receipt: {"ok": True, "stdout": json.dumps(receipt)})
        with pytest.raises(ValueError, match="invalid submission receipt"):
            platform_runner.run_platform_action(
                "chatgpt", "new-turn", config_path=str(config), session_id="caller-session"
            )


def test_async_new_turn_rejects_external_session_options(tmp_path):
    import pytest

    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello"}))
    with pytest.raises(ValueError, match="cannot use browser session options"):
        platform_runner.run_platform_action(
            "chatgpt", "new-turn", config_path=str(config), session_id="caller-session"
        )
    with pytest.raises(ValueError, match="cannot use browser session options"):
        platform_runner.run_platform_action(
            "chatgpt", "new-turn", config_path=str(config), auto_session=True
        )


def test_sync_new_turn_preserves_delivery_error(monkeypatch, tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello", "mode": "sync"}))
    monkeypatch.setattr(chatgpt_delivery_errors, "LOG", tmp_path / "errors.jsonl")
    monkeypatch.setattr(platform_runner, "request", lambda _: {"ok": False, "error": "send blocked"})
    result = platform_runner.run_platform_action(
        "chatgpt", "new-turn", config_path=str(config), session_id="caller-session"
    )
    assert result["result"]["ok"] is False
    assert result["result"]["code"] == "delivery_failed"
    assert "error" not in result["result"]
    assert result["result"].get("status") != "submitted"


def test_sync_new_turn_requires_caller_owned_session(tmp_path):
    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello"}))
    import pytest

    with pytest.raises(ValueError, match="caller-owned --session-id"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config), mode="sync")


def test_new_turn_accepts_only_exact_mode_strings_and_rejects_legacy_sync(monkeypatch, tmp_path):
    import pytest

    for value in (None, True, False, 1, [], {}, "ASYNC", "async ", "sync ", "other"):
        config = tmp_path / "turn.json"
        payload = {"thread_id": "t", "message": "hello", "mode": value}
        config.write_text(json.dumps(payload))
        with pytest.raises(ValueError, match="mode must be exactly"):
            platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))

    config = tmp_path / "turn.json"
    config.write_text(json.dumps({"thread_id": "t", "message": "hello", "sync": False}))
    with pytest.raises(ValueError, match="sync is no longer supported"):
        platform_runner.run_platform_action("chatgpt", "new-turn", config_path=str(config))


def test_cli_documents_string_mode_contract():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "src/cli.py"), "platform", "run", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--mode {async,sync}" in result.stdout
    assert "--sync" not in result.stdout
    assert "caller-owned --session-id" in result.stdout
    assert "mode async" in result.stdout
    assert "mode sync" in result.stdout
    invalid = subprocess.run(
        [sys.executable, str(root / "src/cli.py"), "platform", "run", "chatgpt", "new-turn", "--mode", "SYNC"],
        capture_output=True, text=True,
    )
    assert invalid.returncode == 2
    assert "choose from" in invalid.stderr
    assert "async" in invalid.stderr and "sync" in invalid.stderr


def test_distribution_versions_match_daemon_version_source():
    import importlib.util
    import session_client
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "browser_workspace_app", root / "src/__init__.py", submodule_search_locations=[str(root / "src")]
    )
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    assert tomllib.loads((root / "pyproject.toml").read_text())["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "browser_workspace_app.__version__"}
    assert session_client.package_version() == package.__version__
