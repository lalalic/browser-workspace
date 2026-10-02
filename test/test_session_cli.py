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
    assert "add_parser('status')" in src
    for command in ("tabs", "screenshot", "open", "workspace"):
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
    assert "RUNTIME_DIR/'venv'/package_version()/'bin/python'" in client
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


def test_workspace_lifecycle_is_product_admin_only():
    cli = (ROOT / "bin/browser-workspace").read_text()
    daemon = (ROOT / "session_daemon.py").read_text()
    admin = (ROOT / "node/admin.mjs").read_text()
    assert "sys.argv[1] == 'workspace'" not in cli
    assert "'op':'workspace-create'" not in cli
    assert "'op':'workspace-delete'" not in cli
    assert "workspace-create" in admin
    assert "workspace-delete" in admin
    assert "if op=='workspace-create'" in daemon
    assert "if op=='workspace-delete'" in daemon

def test_npm_package_exposes_browser_workspace_bin_and_persistent_runtime():
    package = (ROOT / "package.json").read_text()
    client = (ROOT / "session_client.py").read_text()
    assert '"browser-workspace": "bin/browser-workspace"' in package
    assert "RUNTIME_DIR/'packages'/package_version()" in client
    assert "RUNTIME_DIR/'venv'/package_version()/'bin/python'" in client
    assert "str(SOURCE/'session_daemon.py')" in client

def test_npm_publish_workflow_uses_oidc():
    workflow = (ROOT / ".github/workflows/npm-publish.yml").read_text()
    assert "id-token: write" in workflow
    assert "npm publish --access public" in workflow
