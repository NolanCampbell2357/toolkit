# Dev Setup

How to set up this toolkit on a new machine.

## Prerequisites

- macOS
- [Homebrew](https://brew.sh)
- git
- [uv](https://docs.astral.sh/uv/) (`brew install uv`). It manages Python, so a separate Python install isn't needed.
- [Claude Code](https://claude.com/claude-code)

## 1. Clone the repo

The `git refresh` alias hardcodes `~/repos/toolkit`, so clone it there:

```sh
mkdir -p ~/repos && cd ~/repos
git clone <repo-url> toolkit
cd toolkit
```

If you clone elsewhere, update the paths in the `refresh` alias in `configs/gitconfig`.

## 2. Install Python dependencies

```sh
uv sync
```

This creates `.venv/` and installs from `pyproject.toml` (Python >= 3.13; uv fetches it if needed). The project is not a package (`package = false`), so it is only an environment for the scripts in `devops/`.

## 3. Git config

Include the toolkit's aliases in your global git config:

```sh
git config --global include.path ~/repos/toolkit/configs/gitconfig
```

Check it with `git glog` and `git refresh` (run the latter inside any git repo).

## 4. Claude Code skills, agents, commands, rules, and output styles

```sh
./scripts/link-claude.sh
```

This symlinks each item in `.claude/{skills,agents,commands,rules,output-styles}` into `~/.claude/`. Hook scripts in `.claude/hooks/` aren't linked; register them in a `settings.json`. Re-run it after adding new ones. `./scripts/unlink-claude.sh` removes the links.

## 5. MCP servers

MCP server configs live in `mcps/`. It's empty for now. Document setup steps for each server here as you add them.

## Verify

- `git refresh` prints the repo root and branch.
- `ls -l ~/.claude/skills ~/.claude/agents` shows symlinks into `~/repos/toolkit/.claude/`.
- `uv run python devops/git_refresh.py` runs without errors inside a git repo.

## Adding new tools

- New Python scripts go in `devops/`. Run them with `uv run`.
- Add dependencies with `uv add <package>` and commit `pyproject.toml` and `uv.lock`.
- Expose a script as a git alias in `configs/gitconfig`.
