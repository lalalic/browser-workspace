import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_contract_source_has_tools_and_workspace():
    src=(ROOT/'mcp/server.py').read_text()
    tree=ast.parse(src)
    assert 'session.start' in src and 'session.exec' in src and 'session.stop' in src
    assert 'workspace' in src

def test_agent_helper_dynamic_workspace_symbols():
    src=(ROOT/'browser-harness/agent_helpers.py').read_text()
    assert 'workspace_set_name' in src and 'workspace_reset_name' in src
    assert 'ContextVar' in src


def test_exec_requires_browser_harness_skill_ack_source():
    src=(ROOT/'mcp/server.py').read_text()
    assert 'browser_harness_skill_loaded' in src
    assert 'Before the first session.exec, load the browser-harness skill' in src
    assert 'self.skill_loaded=False' in src
