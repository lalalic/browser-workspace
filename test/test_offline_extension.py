"""A standalone WebHelm Skill can prepare its published-identity extension offline."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

SKILL = Path(__file__).resolve().parents[1] / "skills/webhelm"
EXTENSION = SKILL / "extension"
OFFICIAL_ID = "kkkpgmhpoeceojalkpfdidffdfnlgdog"
OFFICIAL_URL = (
    "https://chromewebstore.google.com/detail/"
    "browser-workspace/kkkpgmhpoeceojalkpfdidffdfnlgdog"
)
FILES = (
    "manifest.json", "service-worker.mjs", "workspace-manager.mjs",
    "workspace.html", "workspace-page.mjs",
)


def run_installer(skill: Path, home: Path, root: Path | None = None):
    env = {**os.environ, "HOME": str(home)}
    if root is not None:
        env["WEBHELM_OFFLINE_EXTENSION_HOME"] = str(root)
    else:
        env.pop("WEBHELM_OFFLINE_EXTENSION_HOME", None)
    return subprocess.run(
        ["/bin/sh", str(skill / "scripts/prepare-local-extension.sh")],
        env=env, capture_output=True, text=True, check=False,
    )


def test_offline_extension_matches_published_identity_and_source():
    assert not (SKILL.parent.parent / "extension").exists(), "the extension must have one source tree"
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    assert manifest["version"] == "0.3.1"
    assert "update_url" not in manifest  # local unpacked installs do not auto-update
    assert "key" in manifest
    key = base64.b64decode(manifest["key"], validate=True)
    sha = hashlib.sha256(key).hexdigest()[:32]
    extension_id = "".join(chr(ord("a") + int(nibble, 16)) for nibble in sha)
    assert extension_id == OFFICIAL_ID
    assert {f.name for f in EXTENSION.iterdir()} == set(FILES)


def test_skill_prefers_exact_webstore_url_and_documents_offline_approval():
    guide = (SKILL / "SKILL.md").read_text()
    assert OFFICIAL_URL in guide
    assert OFFICIAL_URL in (SKILL.parent.parent / "README.md").read_text()
    assert 'sh "$SKILL_DIR/scripts/prepare-local-extension.sh"' in guide
    assert "chrome://extensions" in guide
    assert "Load unpacked" in guide
    assert "does not auto-update" in guide
    assert "--load-extension" in guide
    assert "managed Chrome" in guide


def test_installer_from_arbitrary_skill_location_is_repeatable_and_offline(tmp_path):
    skill = tmp_path / "agent located anywhere/Some Different Skill Folder"
    skill.mkdir(parents=True)
    shutil.copytree(SKILL / "scripts", skill / "scripts")
    shutil.copytree(SKILL / "extension", skill / "extension")
    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "offline extensions"
    for _ in range(2):
        result = run_installer(skill, home, root)
        assert result.returncode == 0, result.stderr
        assert OFFICIAL_ID in result.stdout
        assert "Load unpacked" in result.stdout
    installed = root / "browser-workspace-0.3.1"
    assert installed.is_dir()
    for name in FILES:
        assert (installed / name).read_bytes() == (skill / "extension" / name).read_bytes()
    assert not (home / "Library/Application Support/Google/Chrome").exists()


def test_installer_refuses_to_replace_tampered_staged_extension(tmp_path):
    home = tmp_path / "home"
    root = tmp_path / "offline"
    assert run_installer(SKILL, home, root).returncode == 0
    installed = root / "browser-workspace-0.3.1"
    (installed / "service-worker.mjs").write_text("user changed")
    result = run_installer(SKILL, home, root)
    assert result.returncode != 0
    assert "refusing overwrite" in result.stderr
    assert (installed / "service-worker.mjs").read_text() == "user changed"


def test_installer_rejects_missing_or_wrong_public_identity(tmp_path):
    skill = tmp_path / "installed"
    skill.mkdir()
    shutil.copytree(SKILL / "scripts", skill / "scripts")
    shutil.copytree(SKILL / "extension", skill / "extension")
    manifest_path = skill / "extension/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["key"] = base64.b64encode(b"a different public key").decode()
    manifest_path.write_text(json.dumps(manifest))
    result = run_installer(skill, tmp_path / "home")
    assert result.returncode != 0
    assert "integrity mismatch: manifest.json" in result.stderr
    assert not (tmp_path / "home/.local/share/webhelm/offline-extensions").exists()


def test_installer_rejects_modified_bundled_code(tmp_path):
    skill = tmp_path / "different location"
    skill.mkdir()
    shutil.copytree(SKILL / "scripts", skill / "scripts")
    shutil.copytree(SKILL / "extension", skill / "extension")
    (skill / "extension/workspace-manager.mjs").write_text("other code")
    result = run_installer(skill, tmp_path / "home")
    assert result.returncode != 0
    assert "integrity mismatch: workspace-manager.mjs" in result.stderr
    assert not (tmp_path / "home/.local/share/webhelm/offline-extensions").exists()
