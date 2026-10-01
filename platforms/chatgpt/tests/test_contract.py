from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "runner"


def test_platform_files_exist():
    assert (ROOT / "manifest.yaml").is_file()
    assert (RUNNER / "_thread_turn.py").is_file()
    assert (RUNNER / "_project_setup.py").is_file()
    assert (RUNNER / "_bootstrap_start.py").is_file()


def test_manifest_uses_browser_workspace_runner():
    text = (ROOT / "manifest.yaml").read_text()
    assert "browser_workspace:" in text
    assert 'runner: "runner/_thread_turn.py"' in text
    assert "browser_harness:" not in text


def test_runner_uses_session_helpers_not_separate_browser_import():
    text = (RUNNER / "_thread_turn.py").read_text()
    assert "from browser_harness" not in text
    assert "switch_tab(target_id)" in text
    assert "new_tab(thread_url)" in text
    assert '"recovered":recovered' in text


def test_project_setup_supports_required_inputs():
    text = (RUNNER / "_project_setup.py").read_text()
    assert "def _ensure_project" in text
    assert "project_reused" in text
    assert "project-only" in text
    assert "def _send_initial" in text
    assert '"thread_url":thread_url' in text


def test_thread_turn_supports_app_attachment():
    text = (RUNNER / "_thread_turn.py").read_text()
    assert "def _attach_app" in text
    assert "app-mention-name" in text


def test_thread_recovery_reuses_bound_target_before_new_lease():
    driver = (RUNNER / "_thread_turn.py").read_text()
    open_thread = driver.split("def _open_thread():",1)[1].split("target_id, recovered=_open_thread()",1)[0]
    assert "goto_url(thread_url)" in open_thread
    assert "target_id=new_tab(thread_url)" in open_thread
    assert open_thread.index("goto_url(thread_url)") < open_thread.index("target_id=new_tab(thread_url)")


def test_prompt_match_tolerates_block_tag_boundary_whitespace():
    ns = {}
    exec((RUNNER / "_readiness.py").read_text(), ns)
    expected = '<FAMILY_TUTOR_CONTEXT>\n{"type":"kid","data":{"message":"hello world"}}\n</FAMILY_TUTOR_CONTEXT>'
    observed = '<FAMILY_TUTOR_CONTEXT>{"type":"kid","data":{"message":"hello world"}}</FAMILY_TUTOR_CONTEXT>'
    assert ns["prompt_text_matches"](observed, expected)
