"""GetPRDiff — 从 GitHub API 获取 PR diff。"""

import urllib.request
import json

from app.config import settings
from app.engine.tools.registry import register_tool


def _parse_owner_repo(git_url: str) -> tuple[str, str]:
    parts = git_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def _github_headers(accept: str) -> dict:
    headers = {"Accept": accept}
    token = settings.github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@register_tool(name="GetPRDiff", toolset="file")
def get_pr_diff(git_url: str, pr_number: int) -> str:
    """从 GitHub API 获取 PR 的 diff。

    Args:
        git_url: GitHub 仓库 URL（如 https://github.com/owner/repo）
        pr_number: PR 编号
    """
    try:
        owner, repo = _parse_owner_repo(git_url)
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        req = urllib.request.Request(url, headers=_github_headers("application/vnd.github.v3.diff"))
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read().decode("utf-8", errors="replace")

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        if e.code == 403 and "rate limit" in body.lower():
            return (
                f"Error: GitHub API rate limit exceeded. "
                f"Set GITHUB_TOKEN in .env for a higher limit (5,000 req/h vs 60 req/h). "
                f"Details: {body}"
            )
        return f"Error: GitHub API returned {e.code}: {body}"
    except Exception as e:
        return f"Error: {e}"


@register_tool(name="GetPRChangedFiles", toolset="file")
def get_pr_changed_files(git_url: str, pr_number: int) -> str:
    """从 GitHub API 获取 PR 变更的文件列表（每行一个路径）。"""
    try:
        owner, repo = _parse_owner_repo(git_url)
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        req = urllib.request.Request(url, headers=_github_headers("application/vnd.github.v3+json"))
        resp = urllib.request.urlopen(req, timeout=30)
        files = json.loads(resp.read().decode("utf-8", errors="replace"))
        return "\n".join(f.get("filename", "") for f in files)

    except Exception as e:
        return f"Error: {e}"
