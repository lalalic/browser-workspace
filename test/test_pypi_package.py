from pathlib import Path
import tomllib


def test_pypi_entrypoint_and_files():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / 'pyproject.toml').read_text())
    assert metadata['project']['scripts']['browser-workspace'] == 'browser_workspace_app.cli:main'
    # Platform sources live at the repository root; setuptools bundles them
    # into the wheel at build time. Do not require the removed source mirror.
    for file in ('platform_runner.py', 'platforms/wechat-channels/manifest.yaml',
                 'session_client.py', 'session_daemon.py', 'managed_chrome.py',
                 'package.json', 'node/admin.mjs', 'setup.py'):
        assert (root / file).is_file(), file
    setup = (root / 'setup.py').read_text()
    assert "copytree(source, target" in setup
    assert "copy2(Path(__file__).resolve().parent / 'platform_runner.py'" in setup
    assert 'PyYAML==6.0.2' in metadata['project']['dependencies']
    assert 'browser-harness==0.1.13' in metadata['project']['dependencies']
    assert not any('git+' in dep for dep in metadata['project']['dependencies'])
    assert not (root / 'src' / 'browser_harness').exists()
    workflow = (root / '.github/workflows/pypi-publish.yml').read_text()
    assert 'browser-workspace platform run chatgpt new-turn --help' in workflow
