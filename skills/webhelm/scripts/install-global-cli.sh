#!/bin/sh
# Called from the installed WebHelm skill, wherever that skill lives.
set -eu

script=$0
while [ -L "$script" ]; do
  parent=$(CDPATH= cd -- "$(dirname -- "$script")" && pwd -P)
  linked=$(readlink "$script")
  case "$linked" in
    /*) script=$linked ;;
    *) script="$parent/$linked" ;;
  esac
done
skill=$(CDPATH= cd -- "$(dirname -- "$script")/.." && pwd -P)
source="$skill/bin/webhelm"
bin="$HOME/.local/bin"
cli="$bin/webhelm"

if [ ! -f "$skill/SKILL.md" ] || ! grep -q '^name: webhelm$' "$skill/SKILL.md" || [ ! -x "$source" ]; then
  echo "This script must be called from an installed WebHelm skill containing an executable bin/webhelm." >&2
  exit 2
fi

mkdir -p "$bin"

if [ -L "$cli" ]; then
  previous=$(readlink "$cli")
  if [ "$previous" != "$source" ]; then
    case "$previous" in
      "$HOME/.local/share/uv/tools/browser-workspace/bin/webhelm")
        backup="$bin/webhelm.previous-uv-tool"
        ;;
      *)
        # Migrate a previous install of this exact skill, not an arbitrary command.
        case "$previous" in
          /*) old_source="$previous" ;;
          *) old_source="$bin/$previous" ;;
        esac
        old_skill=$(CDPATH= cd -- "$(dirname -- "$old_source")/.." 2>/dev/null && pwd -P) || {
          echo "Cannot verify existing webhelm symlink: $previous" >&2
          exit 3
        }
        if [ ! -f "$old_skill/SKILL.md" ] || ! grep -q '^name: webhelm$' "$old_skill/SKILL.md"; then
          echo "Refusing to replace unmanaged webhelm: $cli -> $previous" >&2
          exit 3
        fi
        backup="$bin/webhelm.previous-skill-cli"
        ;;
    esac
    if [ -e "$backup" ] || [ -L "$backup" ]; then
      echo "Previous WebHelm CLI backup already exists: $backup" >&2
      exit 3
    fi
    mv "$cli" "$backup"
    ln -s "$source" "$cli"
  fi
elif [ -e "$cli" ]; then
  echo "Refusing to replace unmanaged webhelm: $cli" >&2
  exit 3
else
  ln -s "$source" "$cli"
fi

# Retire only known obsolete executable links, without deleting their targets.
legacy="$bin/browser-workspace"
if [ -L "$legacy" ]; then
  previous=$(readlink "$legacy")
  case "$previous" in
    "$HOME/.local/share/uv/tools/browser-workspace/bin/browser-workspace" | "$HOME/Workspace/browser-workspace/bin/browser-workspace")
      backup="$bin/browser-workspace.previous-uv-tool"
      if [ -e "$backup" ] || [ -L "$backup" ]; then
        echo "Cannot archive obsolete CLI link: backup exists at $backup" >&2
        exit 3
      fi
      mv "$legacy" "$backup"
      ;;
  esac
fi

echo "Global CLI: $cli -> $source"
case ":$PATH:" in
  *":$bin:"*) ;;
  *) echo "Add $bin to PATH for the agent process." >&2 ;;
esac
