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


def test_default_workspace_is_Harness():
    assert "os.environ['BH_WORKSPACE_NAME'] = 'Harness'" in (ROOT/'session_daemon.py').read_text()
    assert "\"Harness\"" in (ROOT/'agent-workspace/agent_helpers.py').read_text()
    assert 'Default workspace is `Harness`' in (ROOT/'SKILL.md').read_text()


def test_webhelm_help_examples_match_invoked_name():
    import subprocess
    executable=ROOT/'bin/browser-workspace'
    for command in ('webhelm', 'browser-workspace'):
        env=dict(__import__('os').environ)
        env['WEBHELM_CLI_BRAND'] = '1' if command == 'webhelm' else '0'
        for suffix in (['--help'], ['session', '--help'], ['platform', 'run', '--help']):
            result=subprocess.run([str(executable), *suffix], env=env, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            assert f'{command} session start' in result.stdout if suffix != ['platform', 'run', '--help'] else command in result.stdout


def test_skill_documents_webhelm_commands():
    skill=(ROOT/'SKILL.md').read_text()
    assert 'bw() { uvx --from browser-workspace webhelm "$@"; }' in skill
    readme=(ROOT/'README.md').read_text()
    assert 'npx skills add lalalic/browser-workspace --skill webhelm' in readme
    assert 'webhelm session start' in readme
