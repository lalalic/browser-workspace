from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def test_webhelm_skill_metadata_and_npx_install():
    skill=(ROOT/'skills/webhelm/SKILL.md').read_text()
    assert skill.startswith('---\nname: webhelm\n')
    assert 'npx skills add lalalic/browser-workspace --skill webhelm' in skill

def test_python_webhelm_entrypoint():
    from pathlib import Path
    import tomllib
    metadata=tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert metadata['project']['scripts']['webhelm']=='browser_workspace_app.cli:main'
    assert 'browser-workspace' not in metadata['project']['scripts']
    assert '~/.agents/skills/webhelm/scripts/install-global-cli.sh' in (ROOT/'skills/webhelm/SKILL.md').read_text()


def test_default_workspace_is_Harness():
    assert "os.environ['BH_WORKSPACE_NAME'] = 'Harness'" in (ROOT/'src/session_daemon.py').read_text()
    assert "\"Harness\"" in (ROOT/'src/browser-harness/agent_helpers.py').read_text()
    assert 'Default workspace is `Harness`' in (ROOT/'skills/webhelm/SKILL.md').read_text()


def test_webhelm_help_examples_match_invoked_name():
    executable=ROOT/'src/cli.py'
    for suffix in (['--help'], ['session', '--help'], ['platform', 'run', '--help']):
        result=subprocess.run([sys.executable, str(executable), *suffix], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert 'webhelm' in result.stdout


def test_skill_launcher_uses_its_own_platforms_from_any_location(tmp_path):
    import os, shutil
    skill = tmp_path / 'anywhere' / 'webhelm'
    shutil.copytree(ROOT / 'skills/webhelm/bin', skill / 'bin')
    (skill / 'platforms').mkdir()
    fake = tmp_path / 'fakebin'
    fake.mkdir()
    (fake / 'uvx').write_text('#!/bin/sh\necho "$WEBHELM_PLATFORM_DIR|$*"\n')
    (fake / 'uvx').chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith('WEBHELM_')}
    env['PATH'] = f"{fake}:{env['PATH']}"
    result = subprocess.run([str(skill / 'bin/webhelm'), 'platform', 'list'], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{(skill / 'platforms').resolve()}|--from browser-workspace@latest webhelm platform list"


def test_skill_documents_webhelm_commands():
    skill=(ROOT/'skills/webhelm/SKILL.md').read_text()
    assert 'bw() { webhelm "$@"; }' in skill
    readme=(ROOT/'README.md').read_text()
    assert 'npx skills add lalalic/browser-workspace --skill webhelm' in readme
    assert 'webhelm session start' in readme


def test_global_symlink_launcher_resolves_skill_platforms(tmp_path):
    import os, shutil
    skill = tmp_path / 'installed' / 'webhelm'
    shutil.copytree(ROOT / 'skills/webhelm/bin', skill / 'bin')
    (skill / 'platforms').mkdir()
    bindir = tmp_path / 'global-bin'
    bindir.mkdir()
    (bindir / 'webhelm').symlink_to(skill / 'bin/webhelm')
    fake = tmp_path / 'fakebin'
    fake.mkdir()
    (fake / 'uvx').write_text('#!/bin/sh\necho "$WEBHELM_PLATFORM_DIR|$*"\n')
    (fake / 'uvx').chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith('WEBHELM_')}
    env['PATH'] = f"{fake}:{env['PATH']}"
    result = subprocess.run([str(bindir / 'webhelm'), 'platform', 'list'], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{(skill / 'platforms').resolve()}|--from browser-workspace@latest webhelm platform list"
