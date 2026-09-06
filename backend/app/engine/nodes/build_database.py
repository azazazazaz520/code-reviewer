"""Node: 在固定审查快照上建立代码数据库。"""

from __future__ import annotations

from app.engine.code_database import build_review_code_database
from app.engine.coverage import initial_coverage
from app.engine.state import ReviewState
from app.engine.tools.context import TaskToolContext, build_changed_file_refs


def build_database_node(state: ReviewState) -> ReviewState:
    database = build_review_code_database(
        state.get("repo_id", "."),
        state.get("snapshot_revision", ""),
        state.get("snapshot_base_revision", ""),
        log_hook=state.get("_log_hook"),
    )
    state["code_database"] = database
    state["code_database_info"] = database.metadata()
    state["database_status"] = database.database_status
    state["extraction_status"] = database.extraction_status
    state["extraction_errors"] = database.extraction_errors
    state["database_stats"] = database.stats
    state["database_id"] = database.database_id

    refs = build_changed_file_refs(
        state.get("repo_id", "."),
        state.get("changed_files", []),
        revision=state.get("snapshot_revision", ""),
    )
    state["tool_context"] = TaskToolContext(
        repo_root=state.get("repo_id", "."),
        revision=state.get("snapshot_revision", ""),
        database_id=database.database_id,
        approved_context_refs=tuple(refs),
    )
    state["approved_context_refs"] = [ref.as_dict() for ref in refs]
    state["coverage"] = initial_coverage(
        state.get("changed_files", []),
        state.get("raw_diff", ""),
        database_status=database.database_status,
        extraction_status=database.extraction_status,
    )

    if database.database_status != "ready":
        state.setdefault("workflow_errors", []).append(
            {
                "source": "code_database",
                "message": "代码数据库建立失败，报告将标记为 degraded。",
            }
        )
    elif database.extraction_status != "complete":
        state.setdefault("checks", []).append(
            {
                "name": "code_database_extraction",
                "status": "warning",
                "message": f"代码提取部分失败：{len(database.extraction_errors)} 个文件未成功索引。",
            }
        )
    return state
