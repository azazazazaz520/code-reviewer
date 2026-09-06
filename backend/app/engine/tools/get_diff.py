"""GetDiff — 获取 Git diff。"""

import subprocess

from app.engine.tools.registry import register_tool


@register_tool(name="GetDiff", toolset="file")
def get_diff(repo_path: str, base: str = "HEAD~1") -> str:
    """获取指定仓库的 git diff。base 为对比基准，默认 HEAD~1。"""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", base],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout if result.stdout else "(no changes)"
    except FileNotFoundError:
        return "Error: git not found on PATH"
    except Exception as e:
        return f"Error: {e}"


@register_tool(name="GetChangedFiles", toolset="file")
def get_changed_files(repo_path: str, base: str = "HEAD~1") -> str:
    """获取变更文件列表（每行一个路径）。"""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--name-only", "-z", base],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout or "(no changes)"
    except FileNotFoundError:
        return "Error: git not found on PATH"
    except Exception as e:
        return f"Error: {e}"
