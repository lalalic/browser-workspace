#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
EXTENSION_DIR="$ROOT/extension"
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

(
  cd "$TMP_DIR"
  # The publication workflow requires manifest.json to be the first entry.
  # Do not add the root "." directory as the first zip member.
  zip -q "$ZIP" manifest.json
  find . -type f ! -name manifest.json -print | LC_ALL=C sort |
    while IFS= read -r relative; do
      clean=$(printf '%s' "$relative" | sed 's|^\\./||')
      zip -q "$ZIP" "$clean"
    done
)

python3 - "$EXTENSION_DIR/manifest.json" "$ZIP" <<'PY'
import json
import sys
import zipfile
from pathlib import Path

source = json.loads(Path(sys.argv[1]).read_text())
if "key" in source:
    raise SystemExit("extension source must use the official Web Store identity, not a development key")
if source.get("update_url") != "https://clients2.google.com/service/update2/crx":
    raise SystemExit("source manifest must have the Chrome Web Store update URL")

with zipfile.ZipFile(sys.argv[2]) as archive:
    names = archive.namelist()
    if "manifest.json" not in names:
        raise SystemExit("release zip must contain manifest.json at the archive root")
    packaged = json.loads(archive.read("manifest.json"))

if packaged.get("version") != source.get("version"):
    raise SystemExit("packaged manifest version does not match source manifest")
if "key" in packaged:
    raise SystemExit("release zip manifest must not contain a development key")
if packaged.get("update_url") != source.get("update_url"):
    raise SystemExit("release zip must preserve the official Web Store update URL")
PY

echo "$ZIP"
