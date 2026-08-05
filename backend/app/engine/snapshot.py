"""审查代码快照。

所有审查输入都必须来自同一个不可变 revision：diff、变更文件、文件内容
以及可选的代码图谱都以临时 git worktree 作为根目录。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.services.git_host import GitHostError, get_pull, parse_git_repository, pull_sha


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

    def cleanup(self) -> None:
        """移除 worktree；清理失败时再删除临时目录。"""
        try:
            _run_git(
                self.source_repo,
                ["worktree", "remove", "--force", str(self._worktree)],
            )
        except SnapshotError:
            shutil.rmtree(self._worktree, ignore_errors=True)


def create_review_snapshot(
    repo_path: str,
    *,
    git_url: str = "",
    review_type: str = "local",
    pr_number: int | None = None,
    commit_hash: str | None = None,
    branch: str | None = None,
    base_branch: str | None = None,
) -> ReviewSnapshot:
    """准备 PR 或 Local 审查快照。

    PR 使用 GitHub/Gitee 返回的 base/head SHA；Local 使用指定 commit，未指定时使用
    HEAD 或指定 branch。两者都会创建临时 worktree，调用方必须在 workflow 完成后 cleanup。
    """
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
        base_revision = _fetch_revision(source_repo, metadata["base_sha"])
        diff_range = (base_revision, revision, "...")
    else:
        revision = _resolve_revision(source_repo, commit_hash or branch or "HEAD")
        base_ref = base_branch or f"{revision}^"
        base_revision = _resolve_revision(source_repo, base_ref)
        diff_range = (base_revision, revision, "")

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
            base_revision=base_revision,
            raw_diff=diff,
            changed_files=changed_files,
            _worktree=worktree,
        )
    except Exception:
        shutil.rmtree(worktree, ignore_errors=True)
        raise


def _repository_root(repo_path: str) -> str:
    path = Path(repo_path).expanduser().resolve()
    if not path.is_dir():
        raise SnapshotError(f"本地仓库不存在: {repo_path}")
    return _run_git(str(path), ["rev-parse", "--show-toplevel"])


def _resolve_revision(repo_path: str, revision: str) -> str:
    return _run_git(repo_path, ["rev-parse", "--verify", f"{revision}^{{commit}}"])


def _fetch_revision(
    repo_path: str, revision: str, fallback_ref: str | None = None
) -> str:
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
    output = _run_git(repo_path, ["diff", "--name-only", "--no-ext-diff", *revisions])
    return [line for line in output.splitlines() if line.strip()]


def _run_git(repo_path: str, args: list[str], timeout: int = 60) -> str:
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
    return result.stdout.strip()


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
