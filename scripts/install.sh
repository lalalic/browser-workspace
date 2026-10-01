#!/bin/sh
set -eu

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE="$SKILL_DIR/agent-workspace/.env"
EXTENSION_ID="${BH_WORKSPACE_MANAGER_EXTENSION_ID:-kgbghhigmbpefppgkocgjgnnnbhjchic}"
WORKSPACE_NAME="${BH_WORKSPACE_NAME:-Harness}"
POOL_SIZE="${BH_WORKSPACE_POOL_SIZE:-5}"
BIN_DIR="${BROWSER_WORKSPACE_BIN_DIR:-$HOME/.local/bin}"
VENV="$SKILL_DIR/.venv"

mkdir -p "$SKILL_DIR/agent-workspace" "$BIN_DIR"

if command -v uv >/dev/null 2>&1; then
  [ -x "$VENV/bin/python" ] || uv venv --python 3.11 "$VENV"
  uv pip install --python "$VENV/bin/python" -e "$SKILL_DIR"
else
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install -e "$SKILL_DIR"
fi

ln -sf "$SKILL_DIR/bin/browser-workspace" "$BIN_DIR/browser-workspace"

python3 - "$ENV_FILE" "$EXTENSION_ID" "$WORKSPACE_NAME" "$POOL_SIZE" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
values = {
    "BH_WORKSPACE_MANAGER_EXTENSION_ID": sys.argv[2],
    "BH_WORKSPACE_NAME": sys.argv[3],
    "BH_WORKSPACE_POOL_SIZE": sys.argv[4],
}
lines = path.read_text().splitlines() if path.exists() else []
kept = [line for line in lines if not any(line.startswith(f"{key}=") for key in values)]
kept.extend(f"{key}={value}" for key, value in values.items())
path.write_text("\n".join(kept) + "\n")
PY

echo "Browser Workspace runtime installed in $VENV"
echo "Browser Workspace CLI installed at $BIN_DIR/browser-workspace"
echo "BH_WORKSPACE_NAME=$WORKSPACE_NAME"
echo "BH_WORKSPACE_POOL_SIZE=$POOL_SIZE"
echo "BH_WORKSPACE_MANAGER_EXTENSION_ID=$EXTENSION_ID"
