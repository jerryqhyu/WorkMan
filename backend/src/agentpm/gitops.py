from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import get_settings


class GitError(RuntimeError):
    pass


settings = get_settings()


def run_git(args: list[str], cwd: str | Path) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise GitError(process.stderr.strip() or process.stdout.strip())
    return process.stdout.strip()


def ensure_git_repo(path: str | Path) -> None:
    root = Path(path)
    if not (root / ".git").exists() and not (root / ".git").is_file():
        try:
            run_git(["rev-parse", "--git-dir"], cwd=root)
        except GitError as exc:
            raise GitError(f"Not a git repository: {root}") from exc


def detect_default_branch(repo_path: str | Path) -> str:
    try:
        head = run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_path)
        return head.rsplit("/", 1)[-1]
    except GitError:
        try:
            branch = run_git(["branch", "--show-current"], cwd=repo_path)
            return branch or "main"
        except GitError:
            return "main"


def detect_repo_url(repo_path: str | Path) -> str | None:
    try:
        url = run_git(["remote", "get-url", "origin"], cwd=repo_path)
        return url or None
    except GitError:
        return None


def list_repo_files(repo_path: str | Path, limit: int = 300) -> list[str]:
    try:
        output = run_git(["ls-files"], cwd=repo_path)
    except GitError:
        return []
    files = [line.strip() for line in output.splitlines() if line.strip()]
    return files[:limit]



def sanitize_branch_fragment(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9._/-]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-/")[:80] or "task"



def create_worktree(project_id: str, run_id: str, repo_path: str | Path, base_branch: str, branch_name: str) -> Path:
    repo_root = Path(repo_path)
    destination = settings.worktree_root / project_id / run_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return destination
    try:
        run_git(["fetch", "origin", base_branch], cwd=repo_root)
        base_ref = f"origin/{base_branch}"
    except GitError:
        base_ref = base_branch
    run_git(["worktree", "add", "-b", branch_name, str(destination), base_ref], cwd=repo_root)
    return destination



def remove_worktree(repo_path: str | Path, worktree_path: str | Path) -> None:
    path = Path(worktree_path)
    if not path.exists():
        return
    try:
        run_git(["worktree", "remove", "--force", str(path)], cwd=repo_path)
    except GitError:
        pass



def has_changes(repo_path: str | Path) -> bool:
    status = run_git(["status", "--porcelain"], cwd=repo_path)
    return bool(status.strip())



def changed_files(repo_path: str | Path) -> list[str]:
    status = run_git(["status", "--porcelain"], cwd=repo_path)
    files: list[str] = []
    for line in status.splitlines():
        if len(line) >= 4:
            files.append(line[3:].strip())
    return files



def commit_all(repo_path: str | Path, message: str) -> str:
    run_git(["add", "-A"], cwd=repo_path)
    run_git(["commit", "-m", message], cwd=repo_path)
    return run_git(["rev-parse", "HEAD"], cwd=repo_path)



def push_branch(repo_path: str | Path, branch_name: str) -> None:
    run_git(["push", "-u", "origin", branch_name], cwd=repo_path)



def git_diff(repo_path: str | Path) -> str:
    return run_git(["diff", "--", "."], cwd=repo_path)



def git_diff_stat(repo_path: str | Path) -> str:
    try:
        return run_git(["diff", "--stat", "--", "."], cwd=repo_path)
    except GitError:
        return ""
