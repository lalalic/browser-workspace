from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]

def test_webhelm_skill_metadata_and_npx_install():
    skill=(ROOT/'SKILL.md').read_text()
    assert skill.startswith('---\nname: webhelm\n')
    assert 'npx skills add lalalic/browser-workspace --skill webhelm' in skill

def test_webhelm_cli_is_published_and_compatible():
    package=json.loads((ROOT/'package.json').read_text())
    assert package['bin']['webhelm']=='bin/webhelm'
    assert package['bin']['browser-workspace']=='bin/browser-workspace'
    wrapper=ROOT/'bin/webhelm'
    assert wrapper.stat().st_mode & 0o111
    assert 'os.execv' in wrapper.read_text()
