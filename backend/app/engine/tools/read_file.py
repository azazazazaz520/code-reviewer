"""ReadFile — 受任务级快照授权约束的文件读取接口。"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.paths import (
    PathSecurityError,
    file_line_count,
    relative_snapshot_path,
    resolve_snapshot_path,
)
from app.engine.tools.context import TaskToolContext

from app.engine.tools.registry import READ_FILE_MAX_LINES, register_tool


@register_tool(name="ReadFile", toolset="file")
def read_file(file_path: str, start_line: int = 1, max_lines: int = 200) -> str:
    """直接调用时拒绝读取，实际执行必须使用任务级快照上下文。"""
    return "Error: ReadFile requires task snapshot context"


@dataclass(frozen=True)
class FileReadPage:
    """一次经过授权的文件读取结果及其覆盖边界。"""

    file_path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str = ""
    error: str | None = None

    @property
    def complete(self) -> bool:
        return self.error is None and self.end_line >= self.total_lines

    def render(self) -> str:
        if self.error:
            return self.error
        state = "complete" if self.complete else "truncated"
        return (
            f"[ReadFile lines {self.start_line}-{self.end_line}/{self.total_lines}; "
            f"{state}]\n{self.content}"
        )


def _error_page(file_path: str, message: str) -> FileReadPage:
    return FileReadPage(
        file_path=file_path,
        start_line=0,
        end_line=0,
        total_lines=0,
        error=message,
    )


def read_file_page_in_context(
    context: TaskToolContext,
    file_path: str,
    start_line: int = 1,
    max_lines: int = 200,
) -> FileReadPage:
    """读取已批准的快照文件页，并返回精确的行覆盖信息。"""
    normalized_path = "<invalid-path>"
    try:
        try:
            normalized_path = relative_snapshot_path(context.repo_root, file_path)
        except PathSecurityError as exc:
            return _error_page(normalized_path, f"Error: {exc}")

        if isinstance(start_line, bool) or isinstance(max_lines, bool):
            return _error_page(normalized_path, "Error: invalid line range")
        if not isinstance(start_line, int) or not isinstance(max_lines, int):
            return _error_page(normalized_path, "Error: invalid line range")
        if start_line < 1 or max_lines < 1 or max_lines > READ_FILE_MAX_LINES:
            return _error_page(normalized_path, "Error: invalid line range")

        path = resolve_snapshot_path(context.repo_root, normalized_path)
        if not path.is_file():
            return _error_page(
                normalized_path,
                f"Error: file not found: {normalized_path}",
            )

        line_count = file_line_count(path)
        if line_count == 0 or start_line > line_count:
            return _error_page(
                normalized_path,
                f"Error: line range is outside file: {normalized_path}",
            )
        effective_end = min(line_count, start_line + max_lines - 1)
        if not context.can_read(normalized_path, start_line, effective_end):
            return _error_page(
                normalized_path,
                f"Error: file context is not approved: {normalized_path}",
            )

        selected_lines: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if line_number < start_line:
                    continue
                if line_number > effective_end:
                    break
                line = raw_line.rstrip("\r\n")
                selected_lines.append(
                    f"{line_number}|{line}"
                )
        content = "\n".join(selected_lines)
        return FileReadPage(
            file_path=normalized_path,
            start_line=start_line,
            end_line=effective_end,
            total_lines=line_count,
            content=content,
        )
    except (FileNotFoundError, OSError):
        return _error_page(
            normalized_path,
            f"Error: file not found: {normalized_path}",
        )
    except PathSecurityError as exc:
        return _error_page(normalized_path, f"Error: {exc}")


def read_file_in_context(
    context: TaskToolContext,
    file_path: str,
    start_line: int = 1,
    max_lines: int = 200,
) -> str:
    """读取已批准的快照文件行范围。"""
    return read_file_page_in_context(
        context,
        file_path,
        start_line=start_line,
        max_lines=max_lines,
    ).render()
