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

(
  cd "$EXTENSION_DIR"
  zip -qr "$ZIP" .
)

echo "$ZIP"
