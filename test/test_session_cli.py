from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_exposes_session_lifecycle_and_platform_runner():
    src = (ROOT / "bin/browser-workspace").read_text()
    assert "add_parser('session')" in src
    assert "add_parser('start')" in src
    assert "add_parser('exec')" in src
    assert "add_parser('stop')" in src
    assert "add_parser('platform')" in src
    assert "add_parser('run')" in src
    assert "--url" in src
    for command in ("status", "tabs", "screenshot", "open"):
        assert f"add_parser('{command}')" not in src


def test_workspace_option_is_hidden_from_normal_help():
    src = (ROOT / "bin/browser-workspace").read_text()
    assert "start.add_argument('--workspace', help=argparse.SUPPRESS)" in src


def test_session_start_supports_internal_workspace_and_url():
    src = (ROOT / "session_daemon.py").read_text()
    assert "def start_session(workspace=None, url=None)" in src
    assert "bh.new_tab(start_url)" in src


def test_agent_helper_dynamic_workspace_symbols():
    src = (ROOT / "agent-workspace/agent_helpers.py").read_text()
    assert "workspace_set_name" in src and "workspace_reset_name" in src
    assert "ContextVar" in src


def test_runtime_is_vendored():
    assert (ROOT / "src/browser_harness/helpers.py").exists()
    assert (ROOT / "src/browser_harness/daemon.py").exists()
    client = (ROOT / "session_client.py").read_text()
    assert "ROOT/'.venv/bin/python'" in client
    assert "BROWSER_HARNESS_SKILL" not in client


def test_session_start_returns_soft_workspace_warning_contract():
    src = (ROOT / "session_daemon.py").read_text()
    assert "workspace_supported" in src
    assert "Browser Workspace extension is not installed" in src
    assert "extension_url" in src


def test_session_tracks_all_created_tabs_for_cleanup():
    src = (ROOT / "session_daemon.py").read_text()
    assert "self.owned_target_ids={target_id}" in src
    assert "self.namespace['new_tab']=self._new_tab" in src
    assert "self.namespace['cdp']=self._cdp" in src
    assert "def absorb_owned_children(session):" in src
    assert "info.get('openerId')" in src
    assert "bh.cdp('Target.closeTarget', targetId=tid)" in src
    assert "'closed_tabs':closed_count" in src


def test_npx_install_self_bootstraps_runtime():
    client = (ROOT / "session_client.py").read_text()
    assert "def ensure_runtime_python():" in client
    assert "shutil.which('uv')" in client
    assert "'venv','--python','3.11'" in client.replace(' ', '')
    assert "runtime_python=ensure_runtime_python()" in client


def test_skill_uses_installed_cli_path_for_npx_skills():
    skill = (ROOT / "SKILL.md").read_text()
    assert 'BW_CLI="$HOME/.agents/skills/browser-workspace/bin/browser-workspace"' in skill
    assert "$BW_CLI session start" in skill
    assert "$BW_CLI platform run" in skill


def test_hidden_workspace_create_command():
    cli = (ROOT / "bin/browser-workspace").read_text()
    daemon = (ROOT / "session_daemon.py").read_text()
    assert "sys.argv[1] == 'create'" in cli
    assert "usage: browser-workspace create <name> [size=5]" in cli
    assert "add_parser('create')" not in cli
    assert "'op':'workspace-create'" in cli
    assert "def create_workspace(name, pool_size=5):" in daemon
    assert "bh.workspace_create(name.strip(), size)" in daemon
    assert "if op=='workspace-create'" in daemon
