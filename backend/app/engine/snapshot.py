"""审查代码快照。

所有审查输入都必须来自同一个不可变 revision：diff、变更文件、文件内容
以及可选的代码图谱都以临时 git worktree 作为根目录。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.services.git_host import GitHostError, get_pull, parse_git_repository, pull_sha
from app.services.repo_sync import (
    is_valid_commit_sha,
    resolve_remote_branch,
    resolve_revision,
)


class SnapshotError(RuntimeError):
    """无法准备可复现审查快照。"""


@dataclass
class ReviewSnapshot:
    """一次审查使用的、可清理的只读代码快照。"""

    repo_root: str
    source_repo: str
    revision: str
    base_revision: str
    raw_diff: str
    changed_files: list[str]
    _worktree: Path = field(repr=False)
    workspace_fingerprint: str | None = None
    workspace_stats: dict[str, int] | None = None

    def cleanup(self) -> None:
        """移除 worktree；清理失败时再删除临时目录。"""
        try:
            _run_git(
                self.source_repo,
                ["worktree", "remove", "--force", str(self._worktree)],
            )
        except SnapshotError:
            shutil.rmtree(self._worktree, ignore_errors=True)


def validate_workspace_path(workspace_path: str) -> str:
    """校验并规范化用户工作区路径，返回 Git 仓库根目录。"""
    return _repository_root(workspace_path)


def create_review_snapshot(
    repo_path: str,
    *,
    git_url: str = "",
    review_type: str = "local",
    source_type: str | None = None,
    pr_number: int | None = None,
    commit_hash: str | None = None,
    branch: str | None = None,
    base_branch: str | None = None,
    head_revision: str | None = None,
    base_revision: str | None = None,
    workspace_path: str | None = None,
    workspace_target: str | None = None,
) -> ReviewSnapshot:
    """准备 PR 或 Local 审查快照。

    PR 使用 GitHub/Gitee 返回的 base/head SHA；远程来源使用已锁定的 SHA；
    workspace 来源会在临时 worktree 中重建用户工作区。调用方必须在 workflow 完成后 cleanup。
    """
    if source_type == "workspace":
        return _create_workspace_snapshot(
            workspace_path or repo_path,
            workspace_target=workspace_target or "working_tree",
            commit_hash=commit_hash,
            base_revision=base_revision,
        )

    source_repo = _repository_root(repo_path)

    if review_type == "pr":
        if not git_url or not pr_number:
            raise SnapshotError("PR 审查需要 git_url 和 pr_number")
        metadata = _get_pr_metadata(git_url, pr_number)
        revision = _fetch_revision(
            source_repo,
            metadata["head_sha"],
            fallback_ref=f"refs/pull/{pr_number}/head",
        )
        resolved_base_revision = _fetch_revision(source_repo, metadata["base_sha"])
        diff_range = (resolved_base_revision, revision, "...")
    else:
        if head_revision:
            revision = _resolve_revision(source_repo, head_revision)
        elif source_type == "remote_latest":
            if not branch:
                raise SnapshotError("远程最新提交审查需要 branch")
            revision = resolve_remote_branch(source_repo, branch)
        elif source_type == "remote_commit":
            revision = resolve_revision(source_repo, commit_hash or "")
        else:
            revision = _resolve_revision(source_repo, commit_hash or branch or "HEAD")

        if base_revision:
            resolved_base_revision = _resolve_revision(source_repo, base_revision)
        else:
            if base_branch:
                resolved_base_revision = _resolve_revision(source_repo, base_branch)
            else:
                resolved_base_revision = _run_git(
                    source_repo,
                    ["rev-parse", "--verify", f"{revision}^"],
                )
        diff_range = (resolved_base_revision, revision, "")

    worktree = Path(tempfile.mkdtemp(prefix="code-review-snapshot-"))
    worktree.rmdir()
    try:
        _run_git(source_repo, ["worktree", "add", "--detach", str(worktree), revision])
        diff = _git_diff(source_repo, diff_range)
        changed_files = _git_changed_files(source_repo, diff_range)
        return ReviewSnapshot(
            repo_root=str(worktree),
            source_repo=source_repo,
            revision=revision,
            base_revision=resolved_base_revision,
            raw_diff=diff,
            changed_files=changed_files,
            _worktree=worktree,
        )
    except Exception:
        shutil.rmtree(worktree, ignore_errors=True)
        raise


def _create_workspace_snapshot(
    workspace_path: str,
    *,
    workspace_target: str,
    commit_hash: str | None,
    base_revision: str | None,
) -> ReviewSnapshot:
    """从用户工作区重建只读快照，不触碰原目录的工作树和 index。"""
    if workspace_target not in {"working_tree", "head_commit", "commit"}:
        raise SnapshotError(f"不支持的工作区目标: {workspace_target}")

    source_repo = _repository_root(workspace_path)
    if workspace_target in {"head_commit", "commit"}:
        revision = _resolve_revision(source_repo, commit_hash or "HEAD")
        resolved_base = (
            _resolve_revision(source_repo, base_revision)
            if base_revision
            else _run_git(source_repo, ["rev-parse", "--verify", f"{revision}^"])
        )
        return _create_commit_snapshot(source_repo, revision, resolved_base)

    before = _capture_workspace_state(source_repo)
    revision = _resolve_revision(source_repo, "HEAD")
    # 工作区模式审查的是 HEAD 之上的未提交内容，基准就是当前 HEAD。
    resolved_base = _resolve_revision(source_repo, base_revision) if base_revision else revision
    worktree = Path(tempfile.mkdtemp(prefix="code-review-workspace-"))
    worktree.rmdir()
    try:
        _run_git(source_repo, ["worktree", "add", "--detach", str(worktree), revision])
        _apply_workspace_changes(source_repo, worktree, before)
        _run_git(str(worktree), ["add", "-A", "--"])
        raw_diff = _run_git(str(worktree), ["diff", "--cached", "--binary", "--no-ext-diff"])
        changed_files = _git_cached_changed_files(str(worktree))
        after = _capture_workspace_state(source_repo)
        if before.fingerprint != after.fingerprint:
            raise SnapshotError("工作区在采集期间发生变化，请重新提交审查")
        return ReviewSnapshot(
            repo_root=str(worktree),
            source_repo=source_repo,
            revision=revision,
            base_revision=resolved_base,
            raw_diff=raw_diff or "(no changes)",
            changed_files=changed_files,
            workspace_fingerprint=before.fingerprint,
            workspace_stats=before.stats,
            _worktree=worktree,
        )
    except Exception:
        try:
            _run_git(source_repo, ["worktree", "remove", "--force", str(worktree)])
        except SnapshotError:
            shutil.rmtree(worktree, ignore_errors=True)
        raise


@dataclass(frozen=True)
class _WorkspaceState:
    fingerprint: str
    diff: bytes
    untracked_files: tuple[str, ...]
    stats: dict[str, int]


def _capture_workspace_state(repo_path: str) -> _WorkspaceState:
    status = _run_git(repo_path, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    diff = _run_git_bytes(repo_path, ["diff", "HEAD", "--binary", "--no-ext-diff"])
    untracked = tuple(
        record[3:]
        for record in status.split("\0")
        if record.startswith("?? ")
    )
    _reject_submodules(repo_path)

    digest = hashlib.sha256()
    digest.update(_run_git(repo_path, ["rev-parse", "HEAD"]).encode("utf-8"))
    digest.update(status.encode("utf-8", errors="replace"))
    digest.update(diff)
    for relative in untracked:
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(_hash_workspace_path(Path(repo_path) / relative).encode("ascii"))

    staged = sum(bool(record and record[0] not in {" ", "?"}) for record in status.split("\0") if record)
    unstaged = sum(bool(record and record[1:2] not in {" ", "?"}) for record in status.split("\0") if record)
    return _WorkspaceState(
        fingerprint=digest.hexdigest(),
        diff=diff,
        untracked_files=untracked,
        stats={
            "staged_files": staged,
            "unstaged_files": unstaged,
            "untracked_files": len(untracked),
        },
    )


def _apply_workspace_changes(repo_path: str, worktree: Path, state: _WorkspaceState) -> None:
    if state.diff:
        _run_git_input(str(worktree), ["apply", "--binary", "--whitespace=nowarn", "-"], state.diff)
    root = Path(repo_path).resolve()
    destination_root = worktree.resolve()
    for relative in state.untracked_files:
        if any(part == ".git" for part in Path(relative).parts):
            raise SnapshotError("工作区未跟踪文件包含 .git 路径，无法安全复制")
        source = (root / relative).absolute()
        destination = (destination_root / relative).absolute()
        _ensure_within(root, source)
        _ensure_within(destination_root, destination)
        if source.is_symlink():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(os.readlink(source), target_is_directory=source.is_dir())
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        else:
            raise SnapshotError(f"未跟踪路径不是普通文件: {relative}")


def _create_commit_snapshot(repo_path: str, revision: str, base_revision: str) -> ReviewSnapshot:
    worktree = Path(tempfile.mkdtemp(prefix="code-review-snapshot-"))
    worktree.rmdir()
    try:
        _run_git(repo_path, ["worktree", "add", "--detach", str(worktree), revision])
        diff_range = (base_revision, revision, "")
        return ReviewSnapshot(
            repo_root=str(worktree),
            source_repo=repo_path,
            revision=revision,
            base_revision=base_revision,
            raw_diff=_git_diff(repo_path, diff_range),
            changed_files=_git_changed_files(repo_path, diff_range),
            _worktree=worktree,
        )
    except Exception:
        shutil.rmtree(worktree, ignore_errors=True)
        raise


def _git_cached_changed_files(repo_path: str) -> list[str]:
    output = _run_git(repo_path, ["diff", "--cached", "--name-only", "-z"])
    return [item for item in output.split("\0") if item]


def _reject_submodules(repo_path: str) -> None:
    entries = _run_git(repo_path, ["ls-files", "--stage", "-z"])
    if any(entry.startswith("160000 ") for entry in entries.split("\0") if entry):
        raise SnapshotError("本地工作区包含 submodule，当前版本暂不支持")


def _hash_workspace_path(path: Path) -> str:
    if path.is_symlink():
        return hashlib.sha256(os.readlink(path).encode("utf-8", errors="surrogateescape")).hexdigest()
    if not path.is_file():
        raise SnapshotError(f"无法读取未跟踪文件: {path.name}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_within(root: Path, path: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SnapshotError("工作区文件路径超出仓库根目录") from exc


def _run_git_input(repo_path: str, args: list[str], payload: bytes) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            input=payload,
            capture_output=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise SnapshotError(f"git 操作超时: {' '.join(args)}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()
        raise SnapshotError(f"git {' '.join(args)} 失败: {detail[:500]}")
    return result.stdout


def _repository_root(repo_path: str) -> str:
    path = Path(repo_path).expanduser().resolve()
    if not path.is_dir():
        raise SnapshotError(f"本地仓库不存在: {repo_path}")
    return _run_git(str(path), ["rev-parse", "--show-toplevel"])


def _resolve_revision(repo_path: str, revision: str) -> str:
    return _run_git(
        repo_path,
        ["rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"],
    )


def _validate_fetch_revision(revision: str) -> str:
    """限制 fetch 目标为 Commit SHA，避免 Git 将其解释为选项。"""
    if not is_valid_commit_sha(revision):
        raise SnapshotError("审查 revision 必须是有效 Commit SHA")
    return revision


def _fetch_revision(
    repo_path: str, revision: str, fallback_ref: str | None = None
) -> str:
    revision = _validate_fetch_revision(revision)
    try:
        _run_git(repo_path, ["fetch", "--no-tags", "origin", revision])
        return _resolve_revision(repo_path, revision)
    except SnapshotError:
        # 单分支 clone 可能拒绝直接按 SHA 获取；PR head 用显式 ref 兜底。
        if fallback_ref:
            try:
                _run_git(repo_path, ["fetch", "--no-tags", "origin", fallback_ref])
            except SnapshotError:
                raise SnapshotError(f"无法获取审查 revision: {revision}")
            return _run_git(repo_path, ["rev-parse", "--verify", "FETCH_HEAD^{commit}"])
        raise SnapshotError(f"无法获取审查 revision: {revision}")


def _git_diff(repo_path: str, diff_range: tuple[str, str, str]) -> str:
    base, revision, separator = diff_range
    revisions = [f"{base}{separator}{revision}"] if separator else [base, revision]
    return _run_git(repo_path, ["diff", "--no-ext-diff", *revisions]) or "(no changes)"


def _git_changed_files(repo_path: str, diff_range: tuple[str, str, str]) -> list[str]:
    base, revision, separator = diff_range
    revisions = [f"{base}{separator}{revision}"] if separator else [base, revision]
    output = _run_git(
        repo_path,
        ["diff", "--name-only", "-z", "--no-ext-diff", *revisions],
    )
    # NUL 分隔可以保留文件名中的换行；兼容旧测试替换的普通文本返回值。
    return [item for item in output.split("\0") if item] if "\0" in output else [
        line for line in output.splitlines() if line.strip()
    ]


def _run_git(repo_path: str, args: list[str], timeout: int = 60) -> str:
    return _run_git_raw(repo_path, args, timeout).strip()


def _run_git_raw(repo_path: str, args: list[str], timeout: int = 60) -> str:
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
        raise SnapshotError("git not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise SnapshotError(f"git 操作超时: {' '.join(args)}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SnapshotError(f"git {' '.join(args)} 失败: {detail[:500]}")
    return result.stdout


def _run_git_bytes(repo_path: str, args: list[str], timeout: int = 60) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise SnapshotError("git not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise SnapshotError(f"git 操作超时: {' '.join(args)}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode(
            "utf-8", errors="replace"
        ).strip()
        raise SnapshotError(f"git {' '.join(args)} 失败: {detail[:500]}")
    return result.stdout


def _get_pr_metadata(git_url: str, pr_number: int) -> dict[str, str]:
    try:
        provider = parse_git_repository(git_url)
        payload = get_pull(git_url, pr_number)
    except GitHostError as exc:
        raise SnapshotError(str(exc)) from exc
    try:
        return {
            "head_sha": pull_sha(payload, "head"),
            "base_sha": pull_sha(payload, "base"),
        }
    except GitHostError as exc:
        raise SnapshotError(f"{provider.label} PR 元数据缺少 base/head 提交") from exc
