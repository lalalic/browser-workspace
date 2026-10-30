import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src"


def test_single_package_source_and_no_mirrors():
    for file in ("cli.py", "session_client.py", "session_daemon.py", "platform_runner.py",
                 "managed_chrome.py", "admin.mjs", "browser-harness/agent_helpers.py"):
        assert (PACKAGE / file).is_file(), file
    for stale in ("setup.py", "MANIFEST.in", "tools", "platforms", "session_daemon.py",
                  "platform_runner.py", "agent-workspace", "node", "src/browser_workspace_app",
                  "package.json", "bin/browser-workspace", ".github/workflows/npm-publish.yml",
                  PACKAGE / "platforms", PACKAGE / "extension"):
        assert not (ROOT / stale).exists(), stale
    assert not list(PACKAGE.glob("chatgpt_*.py"))


def test_pypi_metadata():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert metadata["project"]["scripts"]["webhelm"] == "browser_workspace_app.cli:main"
    assert "PyYAML==6.0.2" in metadata["project"]["dependencies"]
    assert "browser-harness==0.1.13" in metadata["project"]["dependencies"]
    assert not any("git+" in dep for dep in metadata["project"]["dependencies"])
    assert not (ROOT / "src" / "browser_harness").exists()
    workflow = (ROOT / ".github/workflows/pypi-publish.yml").read_text()
    assert "sync-pypi-package" not in workflow
    assert "WEBHELM_PLATFORM_DIR=skills/webhelm/platforms uvx --from dist/*.whl webhelm platform profile chatgpt" in workflow
