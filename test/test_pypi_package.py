from pathlib import Path
import tomllib


def test_pypi_entrypoint_and_files():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / 'pyproject.toml').read_text())
    assert metadata['project']['scripts']['browser-workspace'] == 'browser_workspace_app.cli:main'
    directory = root / 'src' / 'browser_workspace_app'
    for file in ('cli.py', 'session_client.py', 'session_daemon.py', 'platform_runner.py',
                 'managed_chrome.py', 'package.json', 'pyproject.toml', 'node/admin.mjs',
                 'platforms/wechat-channels/manifest.yaml', 'src/browser_harness/__init__.py'):
        assert (directory / file).is_file(), file
    assert 'PyYAML==6.0.2' in metadata['project']['dependencies']
