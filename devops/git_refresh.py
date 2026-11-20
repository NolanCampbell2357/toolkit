"""git_refresh: refresh the current git repository.

Run via the `git refresh` alias (see configs/gitconfig). Operates on the
repository in the current working directory.
"""

from __future__ import annotations

import subprocess
import sys


def git(*args: str) -> str:
    """Run a git command in the current directory and return stdout."""
    result = subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def main() -> int:
    try:
        root = git("rev-parse", "--show-toplevel")
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
    except subprocess.CalledProcessError:
        print("git refresh: not inside a git repository", file=sys.stderr)
        return 1

    print(f"Refreshing {root} (branch: {branch})")
    # TODO: fetch, prune, update branches, clean up merged branches, etc.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
