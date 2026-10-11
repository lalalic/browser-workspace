from pathlib import Path
import tomllib


def test_pypi_entrypoint_and_files():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / 'pyproject.toml').read_text())
    assert metadata['project']['scripts']['browser-workspace'] == 'browser_workspace_app.cli:main'
    directory = root / 'src' / 'browser_workspace_app'
    for file in ('cli.py', 'session_client.py', 'session_daemon.py', 'platform_runner.py',
                 'managed_chrome.py', 'package.json', 'pyproject.toml', 'node/admin.mjs',
                 'platforms/wechat-channels/manifest.yaml'):
        assert (directory / file).is_file(), file
    assert 'PyYAML==6.0.2' in metadata['project']['dependencies']
    harness = next(dep for dep in metadata['project']['dependencies'] if dep.startswith('browser-harness @ git+'))
    assert 'lalalic/browser-harness.git@80b74e116b9126f5159c84e5e05a750573e5f192' in harness
    assert not (root / 'src' / 'browser_harness').exists()
    assert not (directory / 'src' / 'browser_harness').exists()
