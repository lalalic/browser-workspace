import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin/browser-workspace"


def load_cli(monkeypatch, request_impl):
    session_client = types.ModuleType("session_client")
    session_client.request = request_impl
    platform_runner = types.ModuleType("platform_runner")
    platform_runner.run_platform_action = lambda *args, **kwargs: {"result": {"ok": True}}
    monkeypatch.setitem(sys.modules, "session_client", session_client)
    monkeypatch.setitem(sys.modules, "platform_runner", platform_runner)
    loader = importlib.machinery.SourceFileLoader("browser_workspace_cli_test", str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normal_help_keeps_workspace_group_hidden():
    result = subprocess.run(
        [sys.executable, str(CLI), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "{session,platform}" in result.stdout
    assert "{session,platform,workspace}" not in result.stdout
    assert "\n  workspace" not in result.stdout


def test_old_top_level_create_is_not_a_command():
    result = subprocess.run(
        [sys.executable, str(CLI), "create", "Relay"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "invalid choice: 'create'" in result.stderr


@pytest.mark.parametrize(
    ("argv", "payload"),
    [
        (["workspace", "create", "Relay"], {"op": "workspace-create", "name": "Relay", "pool_size": 5}),
        (["workspace", "create", "Relay", "--size", "6"], {"op": "workspace-create", "name": "Relay", "pool_size": 6}),
        (["workspace", "delete", "Relay"], {"op": "workspace-delete", "name": "Relay", "force": False}),
        (["workspace", "delete", "Relay", "--force"], {"op": "workspace-delete", "name": "Relay", "force": True}),
    ],
)
def test_workspace_commands_send_expected_request(monkeypatch, capsys, argv, payload):
    seen = []

    def request(value):
        seen.append(value)
        if value["op"] == "workspace-delete":
            return {"name": value["name"], "deleted": True}
        return {
            "name": value["name"],
            "poolSize": value["pool_size"],
            "maxCapacity": value["pool_size"],
            "initialized": True,
            "workspace_supported": True,
        }

    cli = load_cli(monkeypatch, request)
    monkeypatch.setattr(sys, "argv", ["browser-workspace", *argv])
    cli.main()

    assert seen == [payload]
    assert json.loads(capsys.readouterr().out)


def test_workspace_runtime_error_is_json_and_nonzero(monkeypatch, capsys):
    cli = load_cli(monkeypatch, lambda _: {"error": "RuntimeError: leased tabs"})
    monkeypatch.setattr(
        sys,
        "argv",
        ["browser-workspace", "workspace", "delete", "Relay"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out) == {"error": "RuntimeError: leased tabs"}


def test_public_session_start_payload_still_regresses(monkeypatch, capsys):
    seen = []

    def request(value):
        seen.append(value)
        return {"session_id": "s1", "workspace": "Harness"}

    cli = load_cli(monkeypatch, request)
    monkeypatch.setattr(
        sys,
        "argv",
        ["browser-workspace", "session", "start", "--url", "https://example.com"],
    )

    cli.main()

    assert seen == [{"op": "start", "workspace": None, "url": "https://example.com"}]
    assert json.loads(capsys.readouterr().out)["session_id"] == "s1"
