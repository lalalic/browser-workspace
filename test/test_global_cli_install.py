"""Global CLI installation follows the installed Skill, whatever its directory."""
import os
import shutil
import subprocess
from pathlib import Path

SKILL_SOURCE = Path(__file__).resolve().parents[1] / "skills/webhelm"


def fixture(tmp_path, location="vendor skills/renamed browser skill"):
    home = tmp_path / "home"
    skill = tmp_path / location
    (skill / "scripts").mkdir(parents=True)
    (skill / "bin").mkdir()
    shutil.copy2(SKILL_SOURCE / "SKILL.md", skill / "SKILL.md")
    shutil.copy2(SKILL_SOURCE / "bin/webhelm", skill / "bin/webhelm")
    shutil.copy2(SKILL_SOURCE / "scripts/install-global-cli.sh", skill / "scripts/install-global-cli.sh")
    bindir = home / ".local/bin"
    bindir.mkdir(parents=True, exist_ok=True)
    legacy = home / ".local/share/uv/tools/browser-workspace/bin"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "webhelm").write_text("legacy uv tool")
    (legacy / "browser-workspace").write_text("legacy executable")
    return home, skill, bindir, legacy


def run(home, skill):
    return subprocess.run(
        ["/bin/sh", str(skill / "scripts/install-global-cli.sh")],
        env={**os.environ, "HOME": str(home)},
        capture_output=True, text=True
    )


def test_arbitrary_location_idempotent_and_global(tmp_path):
    home, skill, bindir, _ = fixture(tmp_path)
    for _ in range(2):
        result = run(home, skill)
        assert result.returncode == 0, result.stderr
    assert (bindir / "webhelm").is_symlink()
    assert os.readlink(bindir / "webhelm") == str(skill / "bin/webhelm")
    assert not (home / ".agents/skills/webhelm").exists()


def test_installer_follows_symlinked_skill_folder(tmp_path):
    home, skill, bindir, _ = fixture(tmp_path)
    alias = tmp_path / "other-agent/plugins/any-name"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(skill, target_is_directory=True)
    assert run(home, alias).returncode == 0
    assert os.readlink(bindir / "webhelm") == str(skill / "bin/webhelm")


def test_migrates_legacy_uv_tool_without_deleting_target(tmp_path):
    home, skill, bindir, legacy = fixture(tmp_path)
    (bindir / "webhelm").symlink_to(legacy / "webhelm")
    (bindir / "browser-workspace").symlink_to(legacy / "browser-workspace")
    result = run(home, skill)
    assert result.returncode == 0, result.stderr
    assert os.readlink(bindir / "webhelm") == str(skill / "bin/webhelm")
    assert (bindir / "webhelm.previous-uv-tool").is_symlink()
    assert (bindir / "browser-workspace.previous-uv-tool").is_symlink()
    assert not (bindir / "browser-workspace").exists()
    assert (legacy / "webhelm").exists()


def test_migrates_previous_skill_from_another_agent_location(tmp_path):
    home, old, bindir, _ = fixture(tmp_path, "old install/anything")
    _, new, _, _ = fixture(tmp_path, "new agent plugins/web-skill")
    (bindir / "webhelm").symlink_to(old / "bin/webhelm")
    result = run(home, new)
    assert result.returncode == 0, result.stderr
    assert os.readlink(bindir / "webhelm") == str(new / "bin/webhelm")
    assert (bindir / "webhelm.previous-skill-cli").is_symlink()


def test_refuses_unmanaged_executable_and_symlink(tmp_path):
    home, skill, bindir, _ = fixture(tmp_path)
    (bindir / "webhelm").write_text("unrelated")
    assert run(home, skill).returncode == 3
    assert (bindir / "webhelm").read_text() == "unrelated"
    (bindir / "webhelm").unlink()
    (bindir / "webhelm").symlink_to("/another/location/elsewhere")
    assert run(home, skill).returncode == 3
    assert os.readlink(bindir / "webhelm") == "/another/location/elsewhere"


def test_install_migrates_known_checkout_shim(tmp_path):
    home, skill, bindir, _ = fixture(tmp_path)
    checkout = home / "Workspace/browser-workspace/bin"
    checkout.mkdir(parents=True)
    (bindir / "browser-workspace").symlink_to(checkout / "browser-workspace")
    result = run(home, skill)
    assert result.returncode == 0, result.stderr
    assert not (bindir / "browser-workspace").exists()
    assert (bindir / "browser-workspace.previous-uv-tool").is_symlink()


def test_skill_has_no_runtime_invocation_or_agent_directory_assumption():
    guide = (SKILL_SOURCE / "SKILL.md").read_text()
    assert "SKILL_DIR=" in guide
    assert 'sh "$SKILL_DIR/scripts/install-global-cli.sh"' in guide
    assert "uvx" not in guide
    assert "~/.agents/skills/webhelm" not in guide
    assert "~/.copilot/skills/webhelm" not in guide
    assert "~/.claude/skills/webhelm" not in guide
    assert "webhelm platform list" in guide
