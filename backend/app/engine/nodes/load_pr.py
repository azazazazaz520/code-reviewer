"""Node: 加载 PR diff 和变更文件列表。

PR 模式：从 GitHub 或 Gitee API 获取 PR diff。
Local 模式：从本地 git 获取 diff。
审查快照已存在时（run_workflow 已准备不可变输入）直接跳过。
"""

from __future__ import annotations

from app.engine.state import ReviewState
from app.engine.tools.get_diff import get_diff, get_changed_files
from app.engine.tools.get_pr_diff import get_pr_diff, get_pr_changed_files


def load_pr_node(state: ReviewState) -> ReviewState:
    if state.get("snapshot_revision"):
        if hook := state.get("_log_hook"):
            hook(
                step="load_pr",
                level="info",
                message=(
                    f"使用审查快照 revision={state['snapshot_revision'][:12]} "
                    f"base={state.get('snapshot_base_revision', '')[:12]}"
                ),
            )
        return state

    review_type = state.get("review_type", "local")
    repo_path = state.get("repo_id", ".")
    pr_number = state.get("pr_number")
    commit_hash = state.get("commit_hash")
    git_url = state.get("git_url", "")

    if hook := state.get("_log_hook"):
        hook(step="load_pr", level="info",
             message=f"正在获取代码变更... (type={review_type})")

    if review_type == "pr" and pr_number and git_url:
        # PR 模式：GitHub/Gitee API
        diff_text = get_pr_diff(git_url, pr_number)
        files_text = get_pr_changed_files(git_url, pr_number)
        if diff_text.startswith("Error:") or files_text.startswith("Error:"):
            raise RuntimeError(diff_text if diff_text.startswith("Error:") else files_text)
    else:
        # Local 模式：本地 git
        base = commit_hash + "~1" if commit_hash else "HEAD~1"
        diff_text = get_diff(repo_path, base)
        if diff_text.startswith("Error: fatal:"):
            diff_text = get_diff(repo_path, "HEAD")
            files_text = get_changed_files(repo_path, "HEAD")
        else:
            files_text = get_changed_files(repo_path, base)

    state["raw_diff"] = diff_text
    state["changed_files"] = [
        f.strip() for f in files_text.split("\n")
        if f.strip() and not f.strip().startswith("Error:")
    ]

    if hook := state.get("_log_hook"):
        hook(step="load_pr", level="info",
             message=f"获取到 {len(state['changed_files'])} 个变更文件")

    return state
