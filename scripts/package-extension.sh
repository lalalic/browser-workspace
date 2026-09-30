#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
EXTENSION_DIR="$ROOT/extension"
DIST_DIR="$ROOT/dist"

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

python3 - "$TMP_DIR/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
manifest = json.loads(path.read_text())
manifest.pop("key", None)
path.write_text(json.dumps(manifest, indent=2) + "\n")
PY

(
  cd "$TMP_DIR"
  zip -qr "$ZIP" .
)

python3 - "$EXTENSION_DIR/manifest.json" "$ZIP" <<'PY'
import json
import sys
import zipfile
from pathlib import Path

source = json.loads(Path(sys.argv[1]).read_text())
if not source.get("key"):
    raise SystemExit("source manifest must retain the development key")

with zipfile.ZipFile(sys.argv[2]) as archive:
    names = archive.namelist()
    if "manifest.json" not in names:
        raise SystemExit("release zip must contain manifest.json at the archive root")
    packaged = json.loads(archive.read("manifest.json"))

if packaged.get("version") != source.get("version"):
    raise SystemExit("packaged manifest version does not match source manifest")
if "key" in packaged:
    raise SystemExit("release zip manifest must not contain the development key")
PY

echo "$ZIP"
