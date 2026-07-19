"""GetPRDiff — 从 GitHub API 获取 PR diff。"""

import os
import urllib.request
import json

from app.engine.tools.registry import register_tool


@register_tool(name="GetPRDiff", toolset="file")
def get_pr_diff(git_url: str, pr_number: int) -> str:
    """从 GitHub API 获取 PR 的 diff。

    Args:
        git_url: GitHub 仓库 URL（如 https://github.com/owner/repo）
        pr_number: PR 编号
    """
    try:
        # 从 git_url 提取 owner/repo
        parts = git_url.rstrip("/").split("/")
        owner, repo = parts[-2], parts[-1]
        if repo.endswith(".git"):
            repo = repo[:-4]

        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github.v3.diff"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read().decode("utf-8", errors="replace")

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        return f"Error: GitHub API returned {e.code}: {body}"
    except Exception as e:
        return f"Error: {e}"


@register_tool(name="GetPRChangedFiles", toolset="file")
def get_pr_changed_files(git_url: str, pr_number: int) -> str:
    """从 GitHub API 获取 PR 变更的文件列表（每行一个路径）。"""
    try:
        parts = git_url.rstrip("/").split("/")
        owner, repo = parts[-2], parts[-1]
        if repo.endswith(".git"):
            repo = repo[:-4]

        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=30)
        files = json.loads(resp.read().decode("utf-8", errors="replace"))
        return "\n".join(f.get("filename", "") for f in files)

    except Exception as e:
        return f"Error: {e}"
