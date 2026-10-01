#!/bin/sh
set -eu

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET_DIR="${BH_AGENT_WORKSPACE:-$HOME/.config/browser-harness/agent-workspace}"
ENV_FILE="$TARGET_DIR/.env"
EXTENSION_ID="${BH_WORKSPACE_MANAGER_EXTENSION_ID:-kgbghhigmbpefppgkocgjgnnnbhjchic}"
WORKSPACE_NAME="${BH_WORKSPACE_NAME:-Harness}"
POOL_SIZE="${BH_WORKSPACE_POOL_SIZE:-5}"
BIN_DIR="${BROWSER_WORKSPACE_BIN_DIR:-$HOME/.local/bin}"

mkdir -p "$TARGET_DIR"
cp "$SKILL_DIR/browser-harness/agent_helpers.py" "$TARGET_DIR/agent_helpers.py"
mkdir -p "$BIN_DIR"
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

echo "Browser Harness workspace helper installed in $TARGET_DIR"
echo "BH_WORKSPACE_NAME=$WORKSPACE_NAME"
echo "BH_WORKSPACE_POOL_SIZE=$POOL_SIZE"
echo "BH_WORKSPACE_MANAGER_EXTENSION_ID=$EXTENSION_ID"
echo "Browser Workspace CLI installed at $BIN_DIR/browser-workspace"
