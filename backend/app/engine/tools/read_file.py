"""ReadFile — 读取文件内容。"""

from pathlib import Path

from app.engine.tools.registry import register_tool


@register_tool(name="ReadFile", toolset="file")
def read_file(file_path: str, start_line: int = 1, max_lines: int = 200) -> str:
    """读取文件内容，可指定起始行和最大行数。"""
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        start = max(0, start_line - 1)
        end = min(len(lines), start + max_lines)
        return "\n".join(f"{i+1}|{line}" for i, line in enumerate(lines[start:end], start))
    except FileNotFoundError:
        return f"Error: file not found: {file_path}"
    except Exception as e:
        return f"Error: {e}"
