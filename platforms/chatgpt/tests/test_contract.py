from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "actions"


def test_platform_files_exist():
    assert (ROOT / "manifest.yaml").is_file()
    assert (ACTIONS / "_thread_turn.py").is_file()
    assert (ACTIONS / "_submit_thread.py").is_file()
    assert (ACTIONS / "_project_setup.py").is_file()
    assert (ACTIONS / "_bootstrap_start.py").is_file()


def test_manifest_declares_actions_and_verification():
    text = (ROOT / "manifest.yaml").read_text()
    assert 'thread-turn: "actions/_thread_turn.py"' in text
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
