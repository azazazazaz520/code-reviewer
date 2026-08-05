"""GetPRDiff — 从 GitHub 或 Gitee API 获取 PR diff。"""

from app.engine.tools.registry import register_tool
from app.services.git_host import GitHostError, get_pull_diff, get_pull_files


@register_tool(name="GetPRDiff", toolset="file")
def get_pr_diff(git_url: str, pr_number: int) -> str:
    """从 GitHub 或 Gitee API 获取 PR 的 diff。

    Args:
        git_url: GitHub 或 Gitee 仓库 URL
        pr_number: PR 编号
    """
    try:
        return get_pull_diff(git_url, pr_number)
    except GitHostError as exc:
        return f"Error: {exc}"


@register_tool(name="GetPRChangedFiles", toolset="file")
def get_pr_changed_files(git_url: str, pr_number: int) -> str:
    """从 GitHub 或 Gitee API 获取 PR 变更的文件列表（每行一个路径）。"""
    try:
        files = get_pull_files(git_url, pr_number)
        return "\n".join(f.get("filename", "") for f in files)
    except GitHostError as exc:
        return f"Error: {exc}"
