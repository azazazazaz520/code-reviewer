"""远程仓库同步与远程分支解析。

该模块只操作应用维护的 clone，不 checkout、merge 或修改其工作区。
所有远程来源都必须经过这里解析为明确的 commit SHA。
"""

from __future__ import annotations

import subprocess
import threading
import re
from dataclasses import dataclass
from pathlib import Path

from app.models.repo import Repo, RepositoryRef


_COMMIT_SHA_PATTERN = re.compile(r"[0-9a-fA-F]{7,64}")


def is_valid_commit_sha(value: str) -> bool:
    """判断输入是否为可安全传给 Git 的 Commit SHA。"""
    return isinstance(value, str) and bool(_COMMIT_SHA_PATTERN.fullmatch(value))


class RepoSyncError(RuntimeError):
    """远程仓库无法同步或解析。"""


@dataclass(frozen=True)
class RemoteBranch:
    name: str
    remote_ref: str
    head_revision: str


@dataclass(frozen=True)
class SyncResult:
    default_branch: str | None
    branches: list[RemoteBranch]


def persist_sync_result(db, repo: Repo, result: SyncResult, checked_at) -> None:
    """将一次成功同步写入仓库和远程引用快照。"""
    previous = {
        ref.name: ref.head_revision
        for ref in db.query(RepositoryRef).filter(RepositoryRef.repo_id == repo.id).all()
    }
    current_names = {branch.name for branch in result.branches}
    for stale in db.query(RepositoryRef).filter(RepositoryRef.repo_id == repo.id).all():
        if stale.name not in current_names:
            db.delete(stale)

    for branch in result.branches:
        ref = (
            db.query(RepositoryRef)
            .filter(
                RepositoryRef.repo_id == repo.id,
                RepositoryRef.name == branch.name,
            )
            .first()
        )
        if ref is None:
            ref = RepositoryRef(repo_id=repo.id, name=branch.name)
            db.add(ref)
        ref.remote_ref = branch.remote_ref
        ref.head_revision = branch.head_revision
        ref.updated_at = checked_at

    repo.default_branch = result.default_branch
    repo.last_synced_at = checked_at
    repo.sync_status = "ready"
    repo.sync_error = None
    return previous


_repo_locks: dict[str, threading.Lock] = {}
_repo_locks_guard = threading.Lock()


def sync_repository(repo_path: str) -> SyncResult:
    """同步 origin 并返回远程分支头；同一 clone 内的 fetch 串行执行。"""
    path = str(Path(repo_path).expanduser().resolve())
    if not Path(path).is_dir():
        raise RepoSyncError(f"审查仓库路径不存在: {repo_path}")

    with _repo_locks_guard:
        lock = _repo_locks.setdefault(path, threading.Lock())
    with lock:
        _run_git(path, ["fetch", "origin", "--prune"], timeout=60)
        return read_remote_refs(path)


def read_remote_refs(repo_path: str) -> SyncResult:
    """读取已同步的 origin 引用，不执行网络操作。"""
    default_branch = _read_default_branch(repo_path)
    output = _run_git(
        repo_path,
        [
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/remotes/origin",
        ],
    )
    branches: list[RemoteBranch] = []
    prefix = "refs/remotes/origin/"
    for line in output.splitlines():
        ref, _, revision = line.partition(" ")
        if not ref.startswith(prefix) or ref.endswith("/HEAD"):
            continue
        name = ref.removeprefix(prefix)
        if name and revision:
            branches.append(RemoteBranch(name, ref, revision))
    return SyncResult(default_branch=default_branch, branches=branches)


def resolve_remote_branch(repo_path: str, branch: str) -> str:
    """只从 refs/remotes/origin 解析分支，拒绝回退到本地同名分支。"""
    clean_branch = branch.removeprefix("origin/").strip()
    if not clean_branch or clean_branch.startswith("refs/"):
        raise RepoSyncError(f"远程分支名称无效: {branch}")
    remote_ref = f"refs/remotes/origin/{clean_branch}"
    return _run_git(repo_path, ["rev-parse", "--verify", f"{remote_ref}^{{commit}}"])


def resolve_revision(repo_path: str, revision: str) -> str:
    """解析已存在的 commit SHA，不接受分支名作为远程最新版本。"""
    if not is_valid_commit_sha(revision):
        raise RepoSyncError("Commit SHA 无效")
    return _run_git(repo_path, ["rev-parse", "--verify", f"{revision.strip()}^{{commit}}"])


def resolve_parent(repo_path: str, revision: str) -> str:
    return _run_git(repo_path, ["rev-parse", "--verify", f"{revision}^{{commit}}^"])


def _read_default_branch(repo_path: str) -> str | None:
    try:
        ref = _run_git(
            repo_path,
            ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
        )
    except RepoSyncError:
        return None
    prefix = "refs/remotes/origin/"
    return ref.removeprefix(prefix) if ref.startswith(prefix) else None


def _run_git(repo_path: str, args: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RepoSyncError("git 未安装或不在 PATH 中") from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoSyncError(f"git 操作超时: {' '.join(args)}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RepoSyncError(f"git {' '.join(args)} 失败: {detail[:500]}")
    return result.stdout.strip()
