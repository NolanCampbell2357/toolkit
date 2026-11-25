# toolkit

My personal development toolkit: shell and git configs, Python devops scripts, MCP server configs, plus Claude Code skills, agents, and context files.

New machine? Start with [`_documentation/devSetup.md`](_documentation/devSetup.md).

## Layout

```
toolkit/
├── configs/          # Dotfiles and tool configs (git aliases, .zshrc, etc.)
│   ├── gitconfig     # Git aliases and settings
│   └── zshrc         # Zsh configuration
├── devops/           # Python scripts, run with uv (e.g. git_refresh.py)
├── mcps/             # MCP server configs
├── scripts/          # Install scripts (link-claude.sh, unlink-claude.sh)
├── _documentation/   # Setup and reference docs (devSetup.md)
├── pyproject.toml    # uv project for the devops scripts
└── .claude/
    ├── skills/       # Claude Code skills
    ├── agents/       # Claude Code subagents
    ├── commands/     # Slash commands
    ├── rules/        # Modular context/instruction files
    ├── hooks/        # Scripts referenced by hooks in settings.json
    └── output-styles/ # Custom output styles
```

## Configs

Files in `configs/` are stored without the leading dot. Symlink them into place so edits here take effect immediately:

```sh
ln -sf "$PWD/configs/zshrc" ~/.zshrc
```

For git, include the aliases from your global config rather than replacing it:

```sh
git config --global include.path "$PWD/configs/gitconfig"
```

Back up any existing file before linking over it.

## Devops scripts

Python scripts in `devops/` run in this repo's uv environment (`uv sync` to set it up). Expose them as git aliases in `configs/gitconfig`. For example, `git refresh` runs `devops/git_refresh.py`, which updates every repo in `~/repos` (fetch and prune, fast-forward behind branches, reset rewritten ones, delete branches whose upstream is gone, report the rest). Use `git refresh --dry-run` to preview, or pass a different folder.

```sh
uv run python devops/git_refresh.py
```

## Claude Code

- **Skills** live in `.claude/skills/<skill-name>/SKILL.md`.
- **Agents** live in `.claude/agents/<agent-name>.md`.
- **Commands** live in `.claude/commands/<command-name>.md` and become `/<command-name>`.
- **Rules** live in `.claude/rules/<topic>.md`: small, focused context files.
- **Output styles** live in `.claude/output-styles/<style>.md`.
- **Hooks**: put hook scripts in `.claude/hooks/` and register them in a `settings.json`. They aren't linked globally.

To use them in every project, symlink them into `~/.claude/`:

```sh
./scripts/link-claude.sh     # link each skill, agent, command, rule, and output style
./scripts/unlink-claude.sh   # remove the links this repo created
```

Each item is linked individually, so anything already in `~/.claude/` is left alone. Edits to existing items show up immediately. Re-run `link-claude.sh` after adding a new item.

## Adding to the toolkit

1. Drop new configs in `configs/`, Python scripts in `devops/`, MCP configs in `mcps/`, and new skills, agents, commands, or rules in `.claude/`.
2. Add a line to this README if it needs setup steps.
3. Commit.

## MCP servers

### `mcps/networktables.py` — FRC NetworkTables 4 client

Tools: `configure`, `connection_status`, `list_topics`, `get_value`, `get_values`, `set_value`, `unpublish`.

Config via env vars: `NT_TEAM` (default `2357`), `NT_HOST` (overrides team, e.g. `localhost` for sim), `NT_PORT`. Also changeable at runtime with the `configure` tool.

Register with Claude Code:

```sh
claude mcp add networktables -e NT_TEAM=2357 -- uv run --project /Users/nolan/repos/toolkit /Users/nolan/repos/toolkit/mcps/networktables.py
```
