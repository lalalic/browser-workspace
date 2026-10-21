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
    assert "from _readiness import" in text
    assert "submission_receipt" in text


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


def test_submission_receipt_requires_accepted_user_turn():
    ns = {}
    exec((ACTIONS / "_readiness.py").read_text(), ns)
    accepted_turn = {"id": "msg_1", "text": "run the repair"}
    assert ns["submission_receipt"]([accepted_turn], 0, "run the repair", "") == {
        "verified_by": "user-turn",
        "turn": accepted_turn,
    }
    assert ns["submission_receipt"]([], 0, "run the repair", "") is None
    assert ns["submission_receipt"]([], 0, "run the repair", "run the repair") is None


def test_submission_failure_preserves_bounded_fallback_diagnostic():
    ns = {}
    exec((ACTIONS / "_readiness.py").read_text(), ns)
    existing_turn = {"id": "old", "text": "old"}
    diagnostic = ns["submission_failure_diagnostic"](
        [existing_turn],
        1,
        "run the repair",
        "run the repair",
        {"composer_present": True, "composer_text_length": 14, "send_enabled": True},
        {"composer_present": False, "composer_text_length": 0, "send_enabled": False},
    )
    assert diagnostic == {
        "accepted": False,
        "reason": "no_accepted_user_turn",
        "user_turn_matched": False,
        "before_user_turn_count": 1,
        "user_turn_count": 1,
        "composer_populated": True,
        "composer_text_length": 14,
        "ui_changed": True,
        "ui_before": {"composer_present": True, "composer_text_length": 14, "send_enabled": True},
        "ui_after": {"composer_present": False, "composer_text_length": 0, "send_enabled": False},
    }


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


def test_wait_until_stable_requires_same_ready_state():
    ns = {}
    exec((ACTIONS / "_readiness.py").read_text(), ns)
    states = iter([{"selector": "textarea"}, {"selector": "#composer"}, {"selector": "#composer"}])
    result = ns["wait_until_stable"](
        lambda: next(states),
        lambda state: bool(state["selector"]),
        timeout=0.2,
        interval=0.001,
        stable_samples=2,
        phase="test",
    )
    assert result == {"selector": "#composer"}


def test_url_prefilled_lifecycle_has_no_composer_dependency():
    text=(ACTIONS / "_lifecycle_common.py").read_text()
    for name in ("composer_selector", "composer_text", "fill_prompt", "wait_for_idle"):
        assert f"def {name}(" not in text
    submit=text.split("def prefilled_submit(",1)[1]
    assert "send_enabled()" in submit
    assert "composer" not in submit.lower()
    assert "send-button-disabled" in submit


def test_submit_thread_is_submission_only():
    text=(ACTIONS/"_submit_thread.py").read_text()
    assert 'project_id' in text and 'thread_id' in text
    assert '?prompt=' in text
    assert 'submission_receipt' in text
    assert 'response_complete' not in text
    assert "app_name" in text and "attach_app_and_restore_prompt" in text


def test_submit_thread_fails_closed_with_diagnostic():
    text = (ACTIONS / "_submit_thread.py").read_text()
    submit = text.split("if not click_visible_send():", 1)[1]
    assert "SubmissionVerificationError" in text
    assert "submission_failure_diagnostic(" in submit
    assert "ui_before" in submit
    assert "composer-cleared" not in text


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
    assert "prefilled_submit" in turn and "submit(message)" in turn
    assert "project_id" in thread and "source_thread_id" in thread
    assert "local-chatgpt" in thread and "thread_id" in thread
    assert "assistant" not in turn.lower().split("print(json.dumps",1)[-1]
    assert "assistant" not in thread.lower().split("print(json.dumps",1)[-1]
    assert "session start" not in turn and "session stop" not in turn
    assert "session start" not in thread and "session stop" not in thread
    assert "prefilled_submit" in common



def test_thread_turn_fails_closed_with_diagnostic():
    text = (ACTIONS / "_thread_turn.py").read_text()
    submit = text.split("def _submit(prompt, files, target_id):", 1)[1].split("def _result(", 1)[0]
    assert "SubmissionVerificationError" in text
    assert "submission_failure_diagnostic(" in submit
    assert "ui_before" in submit
    assert "composer-cleared" not in text



def test_lifecycle_actions_bind_session_helpers_into_imported_module():
    for name in ("_new_turn.py", "_new_thread.py"):
        text=(ACTIONS/name).read_text()
        assert "import _lifecycle_common as lifecycle_common" in text
        assert "lifecycle_common.js = js" in text
        assert "lifecycle_common.fill_input = fill_input" not in text


def test_temporary_new_thread_finishes_without_system_exit():
    thread=(ACTIONS/"_new_thread.py").read_text()
    assert "SystemExit" not in thread
    assert "if temporary:" in thread
    assert "else:" in thread



def test_temporary_submit_recovers_only_before_send_from_prefill_hydration():
    code=(ACTIONS/"_temporary_submit.py").read_text()
    assert 'goto_url(temporary_chat_entry_url())' in code
    assert '"composer readiness was not observed ready" not in str(exc)' in code
    assert 'if not _temporary_chat_enabled():' in code


def test_thread_url_returned_by_new_turn_and_submit_thread():
    from pathlib import Path
    actions = Path(__file__).resolve().parents[1] / "actions"
    for name in ("_new_turn.py", "_submit_thread.py"):
        source = (actions / name).read_text(encoding="utf-8")
        assert "\"thread_url\":thread_url" in source


def test_new_thread_is_chat_only_and_rejects_job_context():
    source=(ACTIONS/"_new_thread.py").read_text()
    assert 'CFG.get("mode", "chat") != "chat"' in source
    assert '"job_id", "jobId", "task_id", "taskId"' in source
    assert "ensure_chat_mode()" in source
    assert "chat.getAttribute('aria-pressed')==='true'" in source
    assert "work.getAttribute('aria-pressed')==='false'" in source
    assert source.index("ensure_chat_mode()") < source.index("receipt=submit(message)")
