#!/bin/sh
# Stage the verified extension files; Chrome installation requires explicit user approval.
set -eu
script=$0
while [ -L "$script" ]; do
  parent=$(CDPATH= cd -- "$(dirname -- "$script")" && pwd -P)
  target=$(readlink "$script")
  case "$target" in /*) script=$target ;; *) script="$parent/$target" ;; esac
done
skill=$(CDPATH= cd -- "$(dirname -- "$script")/.." && pwd -P)
exec node "$skill/scripts/prepare-local-extension.mjs" "$skill/extension" "${WEBHELM_OFFLINE_EXTENSION_HOME:-$HOME/.local/share/webhelm/offline-extensions}"
