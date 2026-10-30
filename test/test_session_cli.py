from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_exposes_session_lifecycle_and_platform_runner():
    src = (ROOT / "src/cli.py").read_text()
    assert "session=sp.add_parser(" in src and "'session'," in src
    assert "start=ssp.add_parser(" in src and "'start'," in src
    assert "ex=ssp.add_parser(" in src and "'exec'," in src
    assert "stop=ssp.add_parser(" in src and "'stop'," in src
    assert "platform=sp.add_parser(" in src and "'platform'," in src
    assert "run=psp.add_parser(" in src and "'run'," in src
    assert "--url" in src
    assert "'status'," in src
    for command in ("tabs", "screenshot", "open", "workspace"):
        assert f"add_parser('{command}')" not in src


def test_workspace_option_is_hidden_from_normal_help():
    src = (ROOT / "src/cli.py").read_text()
    assert "start.add_argument('--workspace', help=argparse.SUPPRESS)" in src


def test_session_start_supports_internal_workspace_and_url():
    src = (ROOT / "src/session_daemon.py").read_text()
    assert "def start_session(workspace=None, url=None)" in src
    assert "bh.new_tab(start_url)" in src


def test_agent_helper_dynamic_workspace_symbols():
    src = (ROOT / "src/browser-harness/agent_helpers.py").read_text()
    assert "workspace_set_name" in src and "workspace_reset_name" in src
    assert "ContextVar" in src


def test_runtime_uses_external_browser_harness_dependency():
    metadata = (ROOT / 'pyproject.toml').read_text()
    assert 'browser-harness==0.1.13' in metadata
    assert not (ROOT / 'src/browser_harness').exists()
    client = (ROOT / 'src/session_client.py').read_text()
    assert "RUNTIME_DIR/'venv'/package_version()/'bin/python'" in client


def test_session_start_returns_soft_workspace_warning_contract():
    src = (ROOT / "src/session_daemon.py").read_text()
    assert "workspace_supported" in src
    assert "Browser Workspace extension is not installed" in src
    assert "extension_url" in src


def test_session_rejects_raw_cdp_target_creation():
    src = (ROOT / "src/session_daemon.py").read_text()
    assert "if method == 'Target.createTarget':" in src
    assert "Target.createTarget is disabled in Browser Workspace sessions" in src
    assert "use new_tab(url)" in src
    assert "self.namespace['cdp']=self._cdp" in src
    assert "def cdp(self, method, **kwargs): return self._session._cdp(method, **kwargs)" in src


def test_session_tracks_all_created_tabs_for_cleanup():
    src = (ROOT / "src/session_daemon.py").read_text()
    assert "self.owned_target_ids={target_id}" in src
    assert "self.namespace['new_tab']=self._new_tab" in src
    assert "self.namespace['cdp']=self._cdp" in src
    assert "def absorb_owned_children(session):" in src
    assert "info.get('openerId')" in src
    assert "bh.close_tab(tid)" in src
    assert "bh.cdp('Target.closeTarget', targetId=tid)" in src
    assert "'closed_tabs':closed_count" in src


def test_npx_install_self_bootstraps_runtime():
    client = (ROOT / "src/session_client.py").read_text()
    assert "def ensure_runtime_python():" in client
    assert "shutil.which('uv')" in client
    assert "'venv','--python','3.11'" in client.replace(' ', '')
    assert "runtime_python=ensure_runtime_python()" in client


def test_skill_uses_published_uvx_cli():
    skill = (ROOT / "skills/webhelm/SKILL.md").read_text()
    launcher = (ROOT / "skills/webhelm/bin/webhelm").read_text()
    assert "browser-workspace@latest" in launcher
    assert "~/.agents/skills/webhelm/scripts/install-global-cli.sh" in skill
    assert "session start" in skill
    assert "platform run" in skill


def test_workspace_lifecycle_is_product_admin_only():
    cli = (ROOT / "src/cli.py").read_text()
    daemon = (ROOT / "src/session_daemon.py").read_text()
    admin = (ROOT / "src/admin.mjs").read_text()
    assert "sys.argv[1] == 'workspace'" not in cli
    assert "'op':'workspace-create'" not in cli
    assert "'op':'workspace-delete'" not in cli
    assert "workspace-create" in admin
    assert "workspace-delete" in admin
    assert "if op=='workspace-create'" in daemon
    assert "if op=='workspace-delete'" in daemon

def test_uvx_runtime_bootstrap_uses_versioned_cache():
    client = (ROOT / "src/session_client.py").read_text()
    assert "target = packages / package_version()" in client
    assert "_same_runtime_files" in client
    assert "RUNTIME_DIR/'venv'/package_version()/'bin/python'" in client
    assert "str(SOURCE/'session_daemon.py')" in client


def test_session_admin_exposes_list_and_stop_all_without_daemon_restart():
    cli = (ROOT / "src/cli.py").read_text()
    daemon = (ROOT / "src/session_daemon.py").read_text()
    assert "ssp.add_parser(" in cli and "'list'," in cli
    assert "stop.add_argument('--all'" in cli
    assert "{'op':'list'}" in cli
    assert "{'op':'stop-all'}" in cli
    assert "def list_sessions():" in daemon
    assert "def stop_all_sessions():" in daemon
    assert "if op=='list': return list_sessions()" in daemon
    assert "if op=='stop-all': return stop_all_sessions()" in daemon
    assert "stop_session(sid)" in daemon
    assert "kill" not in cli.lower()


def test_platform_actions_do_not_use_coordinate_clicks():
    for path in (ROOT / "skills/webhelm/platforms").glob("*/actions/*.py"):
        source = path.read_text()
        assert "click_at_xy(" not in source, f"coordinate click is forbidden in platform code: {path}"


def test_skill_contract_requires_session_self_heal_and_writeback():
    skill = (ROOT / "skills/webhelm/SKILL.md").read_text()
    assert "requires `--session-id` by default" in skill
    assert "--auto-session" in skill and "does not provide orchestrator self-heal" in skill
    assert "Self-heal writeback is mandatory" in skill
    assert "same session" in skill.lower()
    assert "click_at_xy()" in skill
    assert "must not use screen coordinates" in skill


def test_runtime_bootstrap_overlays_exact_harness_revision():
    client = (ROOT / 'src/session_client.py').read_text()
    assert "HARNESS_RUNTIME_SPEC='browser-harness @ git+https://github.com/lalalic/browser-harness.git@80b74e116b9126f5159c84e5e05a750573e5f192'" in client
    assert "'--reinstall',HARNESS_RUNTIME_SPEC" in client
    assert "'--force-reinstall',HARNESS_RUNTIME_SPEC" in client
