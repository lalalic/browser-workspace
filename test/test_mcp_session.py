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



def test_exec_description_requires_browser_harness_skill():
    src=(ROOT/'mcp/server.py').read_text()
    assert 'use/load the `browser-harness` skill' in src
    assert 'browser_harness_skill_loaded' not in src
