#!/bin/sh
set -eu
skill="$HOME/.agents/skills/webhelm"
bin="$HOME/.local/bin"
cli="$bin/webhelm"
source="$skill/bin/webhelm"
[ -f "$skill/SKILL.md" ] && [ -x "$source" ] || { echo "Install global webhelm skill first: npx skills add lalalic/browser-workspace -g -y -s webhelm" >&2; exit 2; }
mkdir -p "$bin"
if [ -L "$cli" ]; then
  current=$(readlink "$cli")
  if [ "$current" != "$source" ]; then
    case "$current" in
      "$HOME/.local/share/uv/tools/browser-workspace/bin/webhelm")
        [ ! -e "$bin/webhelm.previous-uv-tool" ] && [ ! -L "$bin/webhelm.previous-uv-tool" ] || { echo "Old CLI backup already exists" >&2; exit 3; }
        mv "$cli" "$bin/webhelm.previous-uv-tool"
        ln -s "$source" "$cli"
        ;;
      *) echo "Unmanaged CLI at $cli; refusing replacement" >&2; exit 3 ;;
    esac
  fi
elif [ -e "$cli" ]; then
  echo "Unmanaged CLI at $cli; refusing replacement" >&2
  exit 3
else
  ln -s "$source" "$cli"
fi
if [ -L "$bin/browser-workspace" ]; then
  old=$(readlink "$bin/browser-workspace")
  case "$old" in
    "$HOME/.local/share/uv/tools/browser-workspace/bin/browser-workspace" | "$HOME/Workspace/browser-workspace/bin/browser-workspace")
      [ ! -e "$bin/browser-workspace.previous-uv-tool" ] && [ ! -L "$bin/browser-workspace.previous-uv-tool" ] || { echo "Old CLI backup already exists" >&2; exit 3; }
      mv "$bin/browser-workspace" "$bin/browser-workspace.previous-uv-tool" ;;
  esac
fi
echo "Installed: $cli -> $source"
