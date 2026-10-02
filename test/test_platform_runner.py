from pathlib import Path

import platform_runner

ROOT = Path(__file__).resolve().parents[1]


def test_platform_action_resolves_from_actions_directory():
    path = platform_runner.action_path("microsoft-teams", "meeting")
    assert path == ROOT / "platforms" / "microsoft-teams" / "actions" / "_meeting.py"


def test_platform_action_source_gets_sibling_import_path(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    path = ROOT / "platforms" / "microsoft-teams" / "actions" / "_meeting.py"
    source = platform_runner.prepare_action(path, cfg)
    assert "sys.path.insert(0" in source
    assert str(cfg.resolve()) in source


def test_platform_runner_owns_lifecycle_and_hides_session_id(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"action":"status"}')
    calls = []

    def fake_request(payload):
        calls.append(payload)
        if payload["op"] == "start":
            return {
                "session_id": "s1",
                "workspace": "Harness",
                "target_id": "t1",
                "workspace_supported": True,
            }
        if payload["op"] == "exec":
            return {"ok": True, "stdout": "done\n", "stderr": ""}
        if payload["op"] == "stop":
            return {"closed_tabs": 2, "release_error": None}
        raise AssertionError(payload)

    monkeypatch.setattr(platform_runner, "request", fake_request)
    result = platform_runner.run_platform_action(
        "microsoft-teams",
        "meeting",
        config_path=str(cfg),
    )

    assert [call["op"] for call in calls] == ["start", "exec", "stop"]
    assert calls[0]["workspace"] is None
    assert "session_id" not in result
    assert result["workspace_supported"] is True
    assert result["result"]["ok"] is True
    assert result["result"]["cleanup"] == {"closed_tabs": 2, "release_error": None}


def test_platform_runner_stops_after_action_failure(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"action":"status"}')
    calls = []

    def fake_request(payload):
        calls.append(payload)
        if payload["op"] == "start":
            return {"session_id": "s1", "workspace_supported": False, "warning": "soft"}
        if payload["op"] == "exec":
            return {"ok": False, "error": "boom"}
        if payload["op"] == "stop":
            return {"closed_tabs": 1, "release_error": None}
        raise AssertionError(payload)

    monkeypatch.setattr(platform_runner, "request", fake_request)
    result = platform_runner.run_platform_action(
        "microsoft-teams",
        "meeting",
        config_path=str(cfg),
    )

    assert [call["op"] for call in calls] == ["start", "exec", "stop"]
    assert result["warning"] == "soft"
    assert result["result"]["cleanup"]["closed_tabs"] == 1


def test_helper_module_is_not_a_public_platform_action():
    try:
        platform_runner.action_path("chatgpt", "readiness")
    except FileNotFoundError as exc:
        assert "available:" in str(exc)
    else:
        raise AssertionError("helper module became a public platform action")


def test_platform_runner_reuses_caller_owned_session(monkeypatch,tmp_path):
    cfg=tmp_path/'config.json'; cfg.write_text('{"action":"status"}')
    calls=[]
    def fake_request(payload):
        calls.append(payload)
        if payload['op']=='exec': return {'ok':True,'stdout':'done\n','stderr':''}
        raise AssertionError(payload)
    monkeypatch.setattr(platform_runner,'request',fake_request)
    result=platform_runner.run_platform_action('microsoft-teams','meeting',config_path=str(cfg),session_id='owned-session')
    assert [c['op'] for c in calls]==['exec']
    assert calls[0]['session_id']=='owned-session'
    assert result['result']['cleanup']=={'caller_owned_session':True}
