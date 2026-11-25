"""git_refresh: bring every repo in a folder up to date with its remotes.

Run via the `git refresh` alias (see configs/gitconfig).

For each repository directly inside the repos folder (default ~/repos):

1. `git fetch --all --prune` (drops stale remote-tracking refs).
2. For every local branch that has an upstream:
   - behind only            -> fast-forwarded (never a merge)
   - ahead only             -> left alone, reported
   - diverged, but every local commit is already upstream (same patch, e.g.
     after a rebase / force-push) -> reset to the upstream
   - diverged with local-only commits -> left alone, reported
   - upstream deleted ([gone]) -> local branch deleted, even if it has
     unpushed commits (covers squash-merged PRs)

Branches with no upstream are never touched. Worktree directories (where
`.git` is a file) are skipped as repos. A branch checked out in any worktree
(the main one or another) is fast-forwarded / reset inside that worktree, and
only when its tracked files have no changes. A checked-out branch whose
upstream is gone can't be deleted and is reported instead.

Use --dry-run to see what would happen without changing anything.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path.home() / "repos"
DEFAULT_JOBS = 8
SEP = "\x1f"

USE_COLOR = sys.stdout.isatty()


def color(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def green(t: str) -> str:
    return color("32", t)


def yellow(t: str) -> str:
    return color("33", t)


def red(t: str) -> str:
    return color("31", t)


def dim(t: str) -> str:
    return color("2", t)


@dataclass
class Branch:
    name: str
    sha: str
    upstream_ref: str  # full ref, e.g. refs/remotes/origin/main ("" if none)
    upstream: str  # short name, e.g. origin/main
    track: str  # "[gone]", "[ahead 1]", ... or ""
    worktree: str  # path where the branch is checked out ("" if nowhere)


@dataclass
class Result:
    repo: str
    branch: str
    message: str


def git(
    repo: Path, *args: str, check: bool = False
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=check,
        env=env,
    )


def find_repos(root: Path) -> list[Path]:
    """Immediate subdirectories that are real repos (not worktrees)."""
    repos = []
    for child in sorted(root.iterdir()):
        # In a worktree or submodule `.git` is a file, not a directory.
        if child.is_dir() and (child / ".git").is_dir():
            repos.append(child)
    return repos


def list_branches(repo: Path) -> list[Branch]:
    fmt = SEP.join(
        [
            "%(refname:short)",
            "%(objectname)",
            "%(upstream)",
            "%(upstream:short)",
            "%(upstream:track)",
            "%(worktreepath)",
        ]
    )
    out = git(repo, "for-each-ref", f"--format={fmt}", "refs/heads", check=True)
    branches = []
    for line in out.stdout.splitlines():
        name, sha, up_ref, up, track, wt = line.split(SEP)
        branches.append(Branch(name, sha, up_ref, up, track, wt))
    return branches


def is_same_path(a: str, b: Path) -> bool:
    return os.path.realpath(a) == os.path.realpath(str(b))


def tracked_changes(repo: Path) -> bool:
    """True if tracked files have staged or unstaged changes."""
    return bool(
        git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    )


def ahead_behind(repo: Path, b: Branch) -> tuple[int, int]:
    out = git(
        repo,
        "rev-list",
        "--left-right",
        "--count",
        f"{b.name}...{b.upstream_ref}",
        check=True,
    ).stdout.split()
    return int(out[0]), int(out[1])


def has_local_only_commits(repo: Path, b: Branch) -> bool:
    """True if some local commit has no equivalent patch upstream."""
    out = git(repo, "cherry", b.upstream_ref, b.name, check=True).stdout
    return any(line.startswith("+") for line in out.splitlines())


def move_branch(
    repo: Path, b: Branch, worktree: Path | None, mode: str
) -> tuple[bool, str]:
    """Move `b` to its upstream. mode is 'ff' or 'reset'. Returns (ok, error).

    If the branch is checked out in a worktree (the main one or another), the
    move happens inside that worktree so its files stay in sync.
    """
    if worktree is not None:
        if tracked_changes(worktree):
            return False, "checked out with uncommitted changes"
        args = (
            ["merge", "--ff-only", b.upstream_ref]
            if mode == "ff"
            else ["reset", "--hard", b.upstream_ref]
        )
        proc = git(worktree, *args)
    else:
        new = git(repo, "rev-parse", b.upstream_ref, check=True).stdout.strip()
        # Passing the old sha makes update-ref fail if the branch moved meanwhile.
        proc = git(repo, "update-ref", f"refs/heads/{b.name}", new, b.sha)
    if proc.returncode != 0:
        return False, proc.stderr.strip() or proc.stdout.strip()
    return True, ""


def process_branch(
    repo: Path,
    b: Branch,
    dry_run: bool,
    attention: list[Result],
    log: Callable[[str], None],
) -> None:
    if not b.upstream_ref:
        return  # no upstream: never touched

    worktree = Path(b.worktree) if b.worktree else None
    here = worktree is not None and is_same_path(b.worktree, repo)
    elsewhere = worktree is not None and not here
    where = f" ({b.worktree})" if elsewhere else ""
    short = b.sha[:8]

    def flag(msg: str) -> None:
        attention.append(Result(repo.name, b.name, msg))
        log(yellow(f"! {b.name}: {msg}"))

    if b.track == "[gone]":
        if here:
            flag("upstream is gone but branch is checked out; switch away and re-run")
        elif elsewhere:
            flag(f"upstream is gone but branch is checked out in {b.worktree}")
        elif dry_run:
            log(red(f"- {b.name}: would delete (upstream gone, was {short})"))
        else:
            proc = git(repo, "branch", "-D", b.name)
            if proc.returncode == 0:
                log(red(f"- {b.name}: deleted (upstream gone, was {short})"))
            else:
                flag(f"failed to delete: {proc.stderr.strip()}")
        return

    ahead, behind = ahead_behind(repo, b)

    if ahead == 0 and behind == 0:
        return

    if ahead > 0 and behind == 0:
        flag(f"ahead of {b.upstream} by {ahead}, left untouched")
        return

    if ahead == 0:
        action, mode = f"fast-forwarded {behind} commit(s)", "ff"
    elif has_local_only_commits(repo, b):
        flag(
            f"diverged from {b.upstream} (+{ahead}/-{behind}) with local-only commits, left untouched"
        )
        return
    else:
        action, mode = (
            f"reset to {b.upstream} (remote was rewritten, no local-only commits)",
            "reset",
        )

    if dry_run:
        if worktree is not None and tracked_changes(worktree):
            flag(f"checked out{where} with uncommitted changes, left untouched")
        else:
            log(green(f"~ {b.name}: would be {action}"))
        return

    ok, err = move_branch(repo, b, worktree, mode)
    if ok:
        log(green(f"~ {b.name}: {action}{where}"))
    else:
        flag(f"{err}{where}, left untouched")


def process_repo(repo: Path, dry_run: bool) -> tuple[list[str], list[Result]]:
    """Refresh one repo. Returns (output lines, items needing attention).

    Nothing is printed here so repos can be processed in parallel without
    their output interleaving.
    """
    lines: list[str] = [repo.name]
    attention: list[Result] = []

    def log(msg: str) -> None:
        lines.append(f"  {msg}")

    if not git(repo, "remote").stdout.strip():
        log(dim("no remotes, skipped"))
        return lines, attention

    fetch = git(repo, "fetch", "--all", "--prune")
    if fetch.returncode != 0:
        msg = (
            fetch.stderr.strip().splitlines()[-1]
            if fetch.stderr.strip()
            else "fetch failed"
        )
        attention.append(Result(repo.name, "-", f"fetch failed, repo skipped: {msg}"))
        log(red(f"fetch failed, skipped: {msg}"))
        return lines, attention

    try:
        branches = list_branches(repo)
    except subprocess.CalledProcessError as e:
        attention.append(
            Result(repo.name, "-", f"could not list branches: {e.stderr.strip()}")
        )
        log(red(f"could not list branches: {e.stderr.strip()}"))
        return lines, attention

    for b in branches:
        try:
            process_branch(repo, b, dry_run, attention, log)
        except subprocess.CalledProcessError as e:
            attention.append(
                Result(repo.name, b.name, f"git error: {e.stderr.strip()}")
            )
            log(red(f"! {b.name}: git error: {e.stderr.strip()}"))
    return lines, attention


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"folder containing your repos (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would change, change nothing",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=DEFAULT_JOBS,
        help=f"repos to process in parallel (default: {DEFAULT_JOBS})",
    )
    args = parser.parse_args(argv)

    root = args.root.expanduser()
    if not root.is_dir():
        print(f"git refresh: {root} is not a directory", file=sys.stderr)
        return 1

    repos = find_repos(root)
    if not repos:
        print(f"git refresh: no repositories found in {root}")
        return 0

    if args.dry_run:
        print(dim("dry run: nothing will be changed"))

    attention: list[Result] = []
    workers = max(1, min(args.jobs, len(repos)))
    # One worker per repo. Git work is subprocess/network bound, so threads
    # are enough. Each repo's output prints as a block when it finishes.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_repo, r, args.dry_run): r for r in repos}
        for future in as_completed(futures):
            repo = futures[future]
            try:
                lines, repo_attention = future.result()
            except Exception as e:  # noqa: BLE001  # keep one bad repo from killing the run
                lines = [repo.name, red(f"  unexpected error: {e}")]
                repo_attention = [Result(repo.name, "-", f"unexpected error: {e}")]
            print("\n".join(lines), flush=True)
            attention.extend(repo_attention)
    attention.sort(key=lambda r: (r.repo, r.branch))

    print()
    if attention:
        print(yellow(f"Needs your attention ({len(attention)}):"))
        for r in attention:
            print(f"  {r.repo}: {r.branch}: {r.message}")
    else:
        print(green("All repos refreshed, nothing needs attention."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
