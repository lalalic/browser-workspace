from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]

def test_webhelm_skill_metadata_and_npx_install():
    skill=(ROOT/'SKILL.md').read_text()
    assert skill.startswith('---\nname: webhelm\n')
    assert 'npx skills add lalalic/browser-workspace --skill webhelm' in skill

def test_legacy_npm_cli_remains_compatible():
    package=json.loads((ROOT/'package.json').read_text())
    assert package['bin']['browser-workspace']=='bin/browser-workspace'
    assert 'webhelm' not in package['bin']

def test_python_webhelm_entrypoint():
    from pathlib import Path
    import tomllib
    metadata=tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert metadata['project']['scripts']['webhelm']=='browser_workspace_app.cli:main'
    assert metadata['project']['scripts']['browser-workspace']=='browser_workspace_app.cli:main'
    assert 'uvx --from browser-workspace webhelm' in (ROOT/'SKILL.md').read_text()
