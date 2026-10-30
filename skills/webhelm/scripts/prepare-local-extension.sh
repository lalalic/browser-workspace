#!/bin/sh
# Offline fallback. Only stages trusted files; Chrome's user must approve "Load unpacked".
set -eu
source=$0
while [ -L "$source" ]; do
  parent=$(CDPATH= cd -- "$(dirname -- "$source")" && pwd -P)
  target=$(readlink "$source")
  case "$target" in
    /*) source=$target ;;
    *) source="$parent/$target" ;;
  esac
done
skill=$(CDPATH= cd -- "$(dirname -- "$source")/.." && pwd -P)
extension="$skill/extension"
destination="$HOME/.local/share/webhelm/offline-extensions"
if [ -n "$(printenv WEBHELM_OFFLINE_EXTENSION_HOME 2>/dev/null)" ]; then
  destination="$(printenv WEBHELM_OFFLINE_EXTENSION_HOME)"
fi
python3 - "$extension" "$destination" <<'PY'
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

source = Path(sys.argv[1])
root = Path(sys.argv[2])
expected_id = "kkkpgmhpoeceojalkpfdidffdfnlgdog"
filenames = (
    "manifest.json", "service-worker.mjs", "workspace-manager.mjs",
    "workspace.html", "workspace-page.mjs",
)
for filename in filenames:
    if not (source / filename).is_file():
        raise SystemExit(f"Missing bundled WebHelm extension file: {filename}")
# Pinned to the code bytes downloaded from Google's signed published CRX v0.3.1.
# Do not silently ship different code under the same published version.
official_sha256 = {
    "manifest.json": "37287e1df6f187a5e4e686b7b26f943cc894df1f967a191fc917910ecdaa111b",
    "service-worker.mjs": "aff0a4c4724d1427c5a7a121246144a7ef45b1c2d2989fef59911bf297b1422c",
    "workspace-manager.mjs": "bc3cbe3fd3816933411275fc5349b612b92668560b1617db4b68e683452ad851",
    "workspace.html": "92f7a274a99e6185d047ae3dde57273394c6871fa528735e5c17ebbec9b5164a",
    "workspace-page.mjs": "b6a8a32988fde213e0028364332442dfb654f48288d7c73e2407440a6b54181d",
}
for filename, expected in official_sha256.items():
    actual = hashlib.sha256((source / filename).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"Bundled extension file integrity mismatch: {filename}")
manifest = json.loads((source / "manifest.json").read_text())
key = manifest.get("key", "")
try:
    digest = hashlib.sha256(base64.b64decode(key, validate=True)).hexdigest()[:32]
except (ValueError, TypeError) as exc:
    raise SystemExit(f"Invalid offline extension public key: {exc}")
derived_id = "".join(chr(ord("a") + int(c, 16)) for c in digest)
if derived_id != expected_id:
    raise SystemExit("Offline extension does not match the published Chrome Web Store identity")
version = manifest.get("version", "")
if version != "0.3.1" or "update_url" in manifest:
    raise SystemExit("Invalid offline extension manifest/version")
if {p.name for p in source.iterdir()} != set(filenames):
    raise SystemExit("Unexpected files in bundled extension; refusing to install")
root.mkdir(parents=True, exist_ok=True)
destination = root / f"browser-workspace-{version}"

def identical(path):
    return path.is_dir() and {p.name for p in path.iterdir()} == set(filenames) and all(
        (path / name).is_file() and (path / name).read_bytes() == (source / name).read_bytes()
        for name in filenames
    )

if destination.exists() or destination.is_symlink():
    if not identical(destination):
        raise SystemExit(f"Existing offline extension differs: {destination}; refusing overwrite")
else:
    staging = Path(tempfile.mkdtemp(prefix=".webhelm-extension-", dir=root))
    try:
        for name in filenames:
            shutil.copy2(source / name, staging / name)
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

print(f"Verified local Browser Workspace extension {version}")
print(f"Extension ID: {expected_id}")
print(f"Unpacked directory: {destination}")
print("In the managed Chrome window: open chrome://extensions, enable Developer mode,")
print("choose Load unpacked, and select the unpacked directory above.")
print("This prepares local files only. It does not install, replace, or restart Chrome.")
print("An unpacked extension does not receive Chrome Web Store automatic updates.")
PY
