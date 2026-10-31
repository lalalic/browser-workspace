#!/bin/sh
# Install a stable link to the Skill; runtime is resolved independently via npm.
set -eu
script=$0
while [ -L "$script" ]; do
  parent=$(CDPATH= cd -- "$(dirname -- "$script")" && pwd -P)
  linked=$(readlink "$script")
  case "$linked" in /*) script="$linked" ;; *) script="$parent/$linked" ;; esac
done
skill=$(CDPATH= cd -- "$(dirname -- "$script")/.." && pwd -P)
source="$skill/bin/webhelm"
bin="$HOME/.local/bin"
cli="$bin/webhelm"
node -e 'const [maj,min]=process.versions.node.split(".").map(Number);if(maj<22||(maj===22&&min<5))process.exit(1)' || { echo 'WebHelm requires Node >=22.5' >&2; exit 4; }
command -v npx >/dev/null || { echo 'npx is required' >&2; exit 4; }
test -f "$skill/SKILL.md" && test -x "$source" || { echo 'Invalid WebHelm Skill directory' >&2; exit 2; }
mkdir -p "$bin"
if [ -L "$cli" ]; then
  old=$(readlink "$cli")
  case "$old" in "$source") :;;
    "$HOME/.agents/skills/webhelm/bin/webhelm"|"$HOME/.local/share/uv/tools/browser-workspace/bin/webhelm")
      rm "$cli"; ln -s "$source" "$cli";;
    *) echo "Refusing to replace foreign WebHelm symlink: $old" >&2; exit 3;;
  esac
elif [ -e "$cli" ]; then
  echo "Refusing to replace an unmanaged CLI at $cli" >&2; exit 3
else
  ln -s "$source" "$cli"
fi
printf 'Global WebHelm CLI: %s -> %s\n' "$cli" "$source"
