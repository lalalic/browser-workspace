#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Single authoritative extension source, bundled with the installed WebHelm Skill.
EXTENSION_DIR="$ROOT/skills/webhelm/extension"
DIST_DIR="${BROWSER_WORKSPACE_EXTENSION_DIST_DIR:-$ROOT/dist}"

VERSION=$(python3 - "$EXTENSION_DIR/manifest.json" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text())["version"])
PY
)

mkdir -p "$DIST_DIR"
ZIP="$DIST_DIR/browser-workspace-v$VERSION.zip"
rm -f "$ZIP"

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/browser-workspace-package.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM
cp -R "$EXTENSION_DIR/." "$TMP_DIR/"

# Only the generated Web Store upload drops the public unpacked-install key.
# Keep the source manifest and all JavaScript files single-copy in the Skill.
python3 - "$TMP_DIR/manifest.json" <<'PY'
import base64
import hashlib
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
manifest = json.loads(path.read_text())
key = manifest.pop("key", None)
if not isinstance(key, str):
    raise SystemExit("Bundled extension is missing its published public key")
digest = hashlib.sha256(base64.b64decode(key, validate=True)).hexdigest()[:32]
extension_id = "".join(chr(ord("a") + int(char, 16)) for char in digest)
if extension_id != "kkkpgmhpoeceojalkpfdidffdfnlgdog":
    raise SystemExit("Bundled extension public key does not match the published ID")
if "update_url" in manifest:
    raise SystemExit("Unpacked source manifest must not specify update_url")
manifest["update_url"] = "https://clients2.google.com/service/update2/crx"
path.write_text(json.dumps(manifest, indent=2) + "\n")
PY

(
  cd "$TMP_DIR"
  # GitHub release verification expects the manifest at the ZIP root and first.
  zip -q "$ZIP" manifest.json
  find . -type f ! -name manifest.json -print | LC_ALL=C sort |
    while IFS= read -r relative; do
      clean=$(printf '%s' "$relative" | sed 's|^\./||')
      zip -q "$ZIP" "$clean"
    done
)

python3 - "$EXTENSION_DIR/manifest.json" "$ZIP" <<'PY'
import json
import sys
import zipfile
from pathlib import Path

source = json.loads(Path(sys.argv[1]).read_text())
with zipfile.ZipFile(sys.argv[2]) as archive:
    files = archive.namelist()
    if not files or files[0] != "manifest.json":
        raise SystemExit("Generated Chrome Web Store package requires manifest.json first")
    packaged = json.loads(archive.read("manifest.json"))
    if packaged.get("version") != source.get("version"):
        raise SystemExit("Packaged version does not match bundled extension")
    if "key" in packaged:
        raise SystemExit("Chrome Web Store package must not contain unpacked public key")
    if packaged.get("update_url") != "https://clients2.google.com/service/update2/crx":
        raise SystemExit("Chrome Web Store package has incorrect update_url")
    expected = dict(source)
    expected.pop("key", None)
    expected["update_url"] = "https://clients2.google.com/service/update2/crx"
    if packaged != expected:
        raise SystemExit("Chrome Web Store manifest differs from bundled source")
    for item in files[1:]:
        if (Path(sys.argv[1]).parent / item).read_bytes() != archive.read(item):
            raise SystemExit(f"Packaged source differs from bundled extension: {item}")
PY

echo "$ZIP"
