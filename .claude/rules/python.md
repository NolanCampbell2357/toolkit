# Python

Applies to all Python work in this repo (uv project, Python 3.13/3.14).

## Quality gate

After completing a substantial chunk of Python code (new module, multi-file change, large refactor), and before reporting the work as done, run these in order from the repo root:

```sh
uv run ruff format
uv run ruff check --fix
uv run mypy --strict .
```

- Fix anything ruff or mypy reports, then re-run until all three are clean.
- Don't silence errors with blanket `# type: ignore` or `# noqa`. If one is truly needed, make it specific (e.g. `# noqa: BLE001`) and add a short reason.
- Skip the gate for trivial one-line edits; run it before finishing if several accumulated.
- If a failure is pre-existing and unrelated to your change, say so rather than expanding scope.

## Conventions

- Run everything through `uv run`; add dependencies with `uv add` (`uv add --dev` for tooling).
- Full type annotations on all functions (mypy strict is enforced).
- Config lives in `pyproject.toml`.
