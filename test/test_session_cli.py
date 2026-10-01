from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_cli_exposes_only_session_lifecycle():
    src = (ROOT / 'bin/browser-workspace').read_text()
    assert "add_parser('session')" in src
    assert "add_parser('start')" in src
    assert "add_parser('exec')" in src
    assert "add_parser('stop')" in src
    assert "--url" in src
    for command in ("status", "tabs", "screenshot", "open"):
        assert f"add_parser('{command}')" not in src

def test_session_start_supports_workspace_and_url():
    src = (ROOT / 'session_daemon.py').read_text()
    assert 'def start_session(workspace=None, url=None)' in src
    assert "bh.new_tab(start_url)" in src

def test_agent_helper_dynamic_workspace_symbols():
    src = (ROOT / 'agent-workspace/agent_helpers.py').read_text()
    assert 'workspace_set_name' in src and 'workspace_reset_name' in src
    assert 'ContextVar' in src

def test_runtime_is_vendored():
    assert (ROOT / 'src/browser_harness/helpers.py').exists()
    assert (ROOT / 'src/browser_harness/daemon.py').exists()
    client = (ROOT / 'session_client.py').read_text()
    assert "ROOT/'.venv/bin/python'" in client
    assert 'BROWSER_HARNESS_SKILL' not in client


def test_session_start_returns_soft_workspace_warning_contract():
    src = (ROOT / 'session_daemon.py').read_text()
    assert "workspace_supported" in src
    assert "Browser Workspace extension is not installed" in src
    assert "extension_url" in src


def test_session_tracks_all_created_tabs_for_cleanup():
    src = (ROOT / 'session_daemon.py').read_text()
    assert "self.owned_target_ids={target_id}" in src
    assert "self.namespace['new_tab']=self._new_tab" in src
    assert "self.namespace['cdp']=self._cdp" in src
    assert "def absorb_owned_children(session):" in src
    assert "info.get('openerId')" in src
    assert "bh.cdp('Target.closeTarget', targetId=tid)" in src
    assert "'closed_tabs':closed_count" in src
