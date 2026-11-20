#!/usr/bin/env bash
# Symlink each skill and agent in this repo's .claude/ into ~/.claude/.
# Safe to re-run: run it again after adding new skills or agents.
# Existing files that aren't symlinks are skipped, never overwritten.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${CLAUDE_HOME:-$HOME/.claude}"

link_items() {
  local kind="$1"
  local src_dir="$REPO_DIR/.claude/$kind"
  local dest_dir="$TARGET_DIR/$kind"

  mkdir -p "$dest_dir"

  shopt -s nullglob
  for src in "$src_dir"/*; do
    local name dest
    name="$(basename "$src")"
    dest="$dest_dir/$name"

    if [[ -L "$dest" ]]; then
      ln -sfn "$src" "$dest"
      echo "relinked  $kind/$name"
    elif [[ -e "$dest" ]]; then
      echo "skipped   $kind/$name (exists and is not a symlink)"
    else
      ln -s "$src" "$dest"
      echo "linked    $kind/$name"
    fi
  done
  shopt -u nullglob
}

for kind in skills agents commands rules output-styles; do link_items "$kind"; done
