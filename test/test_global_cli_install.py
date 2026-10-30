"""User-wide webhelm installation must be idempotent and preserve unrelated commands."""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/webhelm/scripts/install-global-cli.sh"
SKILL = SCRIPT.parents[1]


def setup(tmp_path):
    home = tmp_path / "home"
    skills = home / ".agents/skills"
    skills.mkdir(parents=True)
    (skills / "webhelm").symlink_to(SKILL, target_is_directory=True)
    bindir = home / ".local/bin"
    bindir.mkdir(parents=True)
    legacy = home / ".local/share/uv/tools/browser-workspace/bin"
    legacy.mkdir(parents=True)
    (legacy / "webhelm").write_text("old")
    (legacy / "browser-workspace").write_text("old")
    return home, bindir, legacy


def run(home):
    return subprocess.run(["/bin/sh", str(SCRIPT)], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)


def test_install_and_reinstall_from_legacy_uv_tool(tmp_path):
    home, bindir, legacy = setup(tmp_path)
    (bindir / "webhelm").symlink_to(legacy / "webhelm")
    (bindir / "browser-workspace").symlink_to(legacy / "browser-workspace")
    assert run(home).returncode == 0
    assert run(home).returncode == 0
    assert os.readlink(bindir / "webhelm") == str(home / ".agents/skills/webhelm/bin/webhelm")
    assert not (bindir / "browser-workspace").exists()
    assert (bindir / "browser-workspace.previous-uv-tool").is_symlink()
    assert (legacy / "webhelm").exists()


def test_refuses_unmanaged_webhelm(tmp_path):
    home, bindir, _ = setup(tmp_path)
    (bindir / "webhelm").write_text("unrelated")
    result = run(home)
    assert result.returncode == 3
    assert (bindir / "webhelm").read_text() == "unrelated"
