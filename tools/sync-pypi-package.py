from pathlib import Path
import shutil
import tomllib

root = Path(__file__).resolve().parents[1]
target = root / 'src' / 'browser_workspace_app'
target.mkdir(parents=True, exist_ok=True)
(target / '__init__.py').write_text('"""Browser Workspace Python distribution."""\n')
for source_name, dest_name in [('bin/browser-workspace', 'cli.py'), ('session_client.py', 'session_client.py'), ('session_daemon.py', 'session_daemon.py'), ('platform_runner.py', 'platform_runner.py'), ('managed_chrome.py', 'managed_chrome.py'), ('package.json', 'package.json'), ('pyproject.toml', 'pyproject.toml')]:
    shutil.copy2(root / source_name, target / dest_name)
for name in ('platforms', 'agent-workspace', 'interaction-skills', 'extension', 'licenses', 'node'):
    shutil.rmtree(target / name, ignore_errors=True)
    shutil.copytree(root / name, target / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store', '.env', '.env.*', '*.pem', '*.key'))
shutil.rmtree(target / 'src' / 'browser_harness', ignore_errors=True)
shutil.copytree(root / 'src' / 'browser_harness', target / 'src' / 'browser_harness', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store', '.env', '.env.*', '*.pem', '*.key'))

# PyPI entry lives directly inside browser_workspace_app, unlike npm bin/.
cli = target / 'cli.py'
cli.write_text(cli.read_text().replace("ROOT=Path(__file__).resolve().parents[1]", "ROOT=Path(__file__).resolve().parent"))
import json
metadata = json.loads((target / 'package.json').read_text())
metadata['version'] = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
(target / 'package.json').write_text(json.dumps(metadata, indent=2) + '\n')
