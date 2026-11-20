#!/usr/bin/env bash
# Remove symlinks in ~/.claude/{skills,agents} that point into this repo.
# Anything that isn't a symlink into this repo is left alone.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${CLAUDE_HOME:-$HOME/.claude}"

for kind in skills agents commands rules output-styles; do
  dest_dir="$TARGET_DIR/$kind"
  [[ -d "$dest_dir" ]] || continue

  shopt -s nullglob
  for dest in "$dest_dir"/*; do
    if [[ -L "$dest" && "$(readlink "$dest")" == "$REPO_DIR/.claude/$kind/"* ]]; then
      rm "$dest"
      echo "removed   $kind/$(basename "$dest")"
    fi
  done
  shopt -u nullglob
done
