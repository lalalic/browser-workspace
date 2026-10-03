from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "actions"


def test_platform_files_exist():
    assert (ROOT / "manifest.yaml").is_file()
    assert (ACTIONS / "_thread_turn.py").is_file()
    assert (ACTIONS / "_new_turn.py").is_file()
    assert (ACTIONS / "_new_thread.py").is_file()
    assert (ACTIONS / "_lifecycle_common.py").is_file()
    assert (ACTIONS / "_submit_thread.py").is_file()
    assert (ACTIONS / "_project_setup.py").is_file()
    assert (ACTIONS / "_bootstrap_start.py").is_file()
    assert (ACTIONS / "_mcp_app.py").is_file()


def test_manifest_declares_actions_and_verification():
    text = (ROOT / "manifest.yaml").read_text()
    assert 'thread-turn: "actions/_thread_turn.py"' in text
    assert 'new-turn: "actions/_new_turn.py"' in text
    assert 'new-thread: "actions/_new_thread.py"' in text
    assert 'submit-thread: "actions/_submit_thread.py"' in text
    assert "verification:" in text
    assert "status: migrated_unverified" in text


def test_action_uses_browser_helpers_without_infrastructure_import():
    text = (ACTIONS / "_thread_turn.py").read_text()
    assert "from browser_harness" not in text
    assert "session_client" not in text
    assert "workspace_set_" not in text
    assert "switch_tab(target_id)" in text
    assert "new_tab(thread_url)" in text
    assert '"recovered":recovered' in text
    assert "from _readiness import wait_until_stable, submission_receipt" in text


def test_project_setup_supports_required_inputs():
    text = (ACTIONS / "_project_setup.py").read_text()
    assert "def _ensure_project" in text
    assert "project_reused" in text
    assert "project-only" in text
    assert "def _send_initial" in text
    assert '"thread_url":thread_url' in text


def test_thread_turn_supports_app_attachment():
    text = (ACTIONS / "_thread_turn.py").read_text()
    assert "def _attach_app" in text
    assert "app-mention-name" in text


def test_thread_recovery_reuses_bound_target_before_new_target():
    driver = (ACTIONS / "_thread_turn.py").read_text()
    open_thread = driver.split("def _open_thread():",1)[1].split("target_id, recovered=_open_thread()",1)[0]
    assert "goto_url(thread_url)" in open_thread
    assert "target_id=new_tab(thread_url)" in open_thread
    assert open_thread.index("goto_url(thread_url)") < open_thread.index("target_id=new_tab(thread_url)")


def test_prompt_match_tolerates_block_tag_boundary_whitespace():
    ns = {}
    exec((ACTIONS / "_readiness.py").read_text(), ns)
    expected = '<FAMILY_TUTOR_CONTEXT>\n{"type":"kid","data":{"message":"hello world"}}\n</FAMILY_TUTOR_CONTEXT>'
    observed = '<FAMILY_TUTOR_CONTEXT>{"type":"kid","data":{"message":"hello world"}}</FAMILY_TUTOR_CONTEXT>'
    assert ns["prompt_text_matches"](observed, expected)


def test_wait_until_stable_retries_transient_read_errors():
    ns = {}
    exec((ACTIONS / "_readiness.py").read_text(), ns)
    calls = {"n": 0}
    def read_state():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("not hydrated")
        return {"ready": True}
    result = ns["wait_until_stable"](
        read_state,
        lambda state: state.get("ready") is True,
        timeout=0.2,
        interval=0.001,
        stable_samples=1,
        phase="test",
    )
    assert result == {"ready": True}
    assert calls["n"] == 3


def test_submit_thread_is_submission_only():
    text=(ACTIONS/"_submit_thread.py").read_text()
    assert 'project_id' in text and 'thread_id' in text
    assert '?prompt=' in text
    assert 'submission_receipt' in text
    assert 'response_complete' not in text
    assert "app_name" in text and "attach_app_and_restore_prompt" in text


def test_manifest_declares_mcp_app_action():
    text = (ROOT / "manifest.yaml").read_text()
    assert 'mcp-app: "actions/_mcp_app.py"' in text
    assert "mcp-app-management" in text
    assert "mcp-tool-refresh" in text


def test_mcp_app_action_uses_semantic_selectors_and_safe_operations():
    text = (ACTIONS / "_mcp_app.py").read_text()
    assert 'Open profile menu' not in text  # direct settings route avoids profile-menu fragility
    assert 'https://chatgpt.com/settings/plugins-settings' in text
    assert "APP_NAME" in text
    assert "text.startsWith(name+" in text
    assert "body.includes('Disconnect')" in text
    assert "body.includes('Permissions')" in text
    assert "texts.includes('Refresh tools')" in text
    assert 'operation must be status, open, or refresh-tools' in text
    assert 'Delete app' not in text
    assert 'Uninstall' in text  # observed only; never clicked


def test_mcp_app_readme_captures_snapshot_first_setup_flow():
    text = (ROOT / "README.md").read_text()
    assert "Configure a custom MCP app" in text
    assert "snapshot(interactive_only=False)" in text
    assert "Permissions" in text and "Disconnect" in text and "Refresh tools" in text
    assert "never commit credentials" in text


def test_lifecycle_actions_use_stable_ids_and_do_not_wait_for_new_answer():
    turn=(ACTIONS/"_new_turn.py").read_text()
    thread=(ACTIONS/"_new_thread.py").read_text()
    common=(ACTIONS/"_lifecycle_common.py").read_text()
    assert "project_id" in turn and "thread_id" in turn
    assert "wait_for_idle" in turn and "submit(message)" in turn
    assert "project_id" in thread and "source_thread_id" in thread
    assert "local-chatgpt" in thread and "thread_id" in thread
    assert "assistant" not in turn.lower().split("print(json.dumps",1)[-1]
    assert "assistant" not in thread.lower().split("print(json.dumps",1)[-1]
    assert "session start" not in turn and "session stop" not in turn
    assert "session start" not in thread and "session stop" not in thread
    assert "submission_receipt" in common


def test_new_thread_supports_projectless_and_temporary_modes():
    thread=(ACTIONS/"_new_thread.py").read_text()
    assert 'temporary=bool(CFG.get("temporary", False))' in thread
    assert 'temporary=true cannot be combined with project_id' in thread
    assert 'https://chatgpt.com/?temporary-chat=true' in thread
    assert 'start_url="https://chatgpt.com/"' in thread
    assert 'Temporary Chat mode was not activated' in thread
    assert '"temporary":True' in thread
    assert '"thread_id":None' in thread


def test_lifecycle_actions_bind_session_helpers_into_imported_module():
    for name in ("_new_turn.py", "_new_thread.py"):
        text=(ACTIONS/name).read_text()
        assert "import _lifecycle_common as lifecycle_common" in text
        assert "lifecycle_common.js = js" in text
        assert "lifecycle_common.fill_input = fill_input" in text


def test_temporary_new_thread_finishes_without_system_exit():
    thread=(ACTIONS/"_new_thread.py").read_text()
    assert "SystemExit" not in thread
    assert "if temporary:" in thread
    assert "else:" in thread


def test_new_turn_project_id_is_optional():
    turn=(ACTIONS/"_new_turn.py").read_text()
    assert 'project_id=str(CFG.get("project_id") or "").strip() or None' in turn
    assert 'if not thread_id: raise RuntimeError("thread_id is required")' in turn
    assert 'https://chatgpt.com/c/{quote(thread_id' in turn
    assert 'https://chatgpt.com/g/{quote(project_id' in turn
