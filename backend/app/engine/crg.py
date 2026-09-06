"""code-review-graph（CRG）集成。

封装图谱构建与影响半径分析；任何失败都静默降级为普通文件上下文，
不中断审查流程。该模块不包含 LLM 逻辑，只负责结构性分析。
"""

from __future__ import annotations

from app.engine.code_database import ReviewCodeDatabase
from app.engine.paths import (
    PathSecurityError,
    file_line_count,
    relative_snapshot_path,
    resolve_snapshot_path,
)
from app.engine.state import ReviewState
from app.engine.tools.context import ApprovedContextRef


def try_crg_context(
    state: ReviewState,
    repo_path: str,
    changed_files: list[str],
) -> bool:
    """尝试构建 CRG 图谱并获取影响半径，成功返回 True。

    失败时返回 False，调用方应回退到按变更文件收集上下文的路径。
    写入的 state 字段：
      - context_candidates：变更文件与受影响文件去重后的候选集合
      - impact_radius：changed_nodes / impacted_nodes / impacted_files 统计
    """
    database = state.get("code_database")
    if not isinstance(database, ReviewCodeDatabase) or not database.ready:
        return False

    try:
        result = database.get_review_context(changed_files)
        if result.get("status") != "ok":
            return False

        ctx = result.get("context", {})
        impacted_files: list[str] = []
        for file_path in ctx.get("impacted_files", []):
            try:
                impacted_files.append(relative_snapshot_path(repo_path, file_path))
            except PathSecurityError:
                continue

        analysis_results: list[dict] = []
        refs: list[ApprovedContextRef] = []
        changed_normalized: list[str] = []
        changed_set = set()
        for changed_file in changed_files:
            try:
                normalized = relative_snapshot_path(repo_path, changed_file)
                if normalized not in changed_set:
                    changed_normalized.append(normalized)
                    changed_set.add(normalized)
            except PathSecurityError:
                continue
        for node in ctx.get("graph", {}).get("impacted_nodes", []):
            node_id = node.get("id")
            if node_id is None:
                continue
            try:
                file_path = relative_snapshot_path(repo_path, node.get("file_path", ""))
                source_path = resolve_snapshot_path(repo_path, file_path)
                if not source_path.is_file():
                    continue
            except PathSecurityError:
                continue
            start_line = max(1, int(node.get("line_start") or 1))
            end_line = max(start_line, int(node.get("line_end") or start_line))
            line_count = file_line_count(source_path)
            if line_count == 0 or start_line > line_count:
                continue
            end_line = min(end_line, line_count)
            result_id = f"{database.database_id}:crg-impact:{node_id}"
            analysis_results.append(
                {
                    "result_id": result_id,
                    "database_id": database.database_id,
                    "revision": database.revision,
                    "rule_id": "crg.impact_radius",
                    "file": file_path,
                    "line_start": start_line,
                    "line_end": end_line,
                    "message": f"CRG 影响范围包含 {node.get('qualified_name') or node.get('name')}",
                    "evidence_refs": [result_id],
                }
            )
            if file_path not in changed_set:
                refs.append(
                    ApprovedContextRef(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        source="query_result",
                        result_id=result_id,
                        rule_id="crg.impact_radius",
                        database_id=database.database_id,
                    )
                )

        state["analysis_results"] = list(state.get("analysis_results", [])) + analysis_results
        tool_context = state.get("tool_context")
        if tool_context is not None:
            tool_context = tool_context.with_refs(refs)
            state["tool_context"] = tool_context
            state["approved_context_refs"] = [
                ref.as_dict() for ref in tool_context.approved_context_refs
            ]
        related_set = {ref.file_path for ref in refs}
        impacted_files = [
            file_path for file_path in impacted_files
            if file_path in changed_set or file_path in related_set
        ]
        state["context_candidates"] = list(dict.fromkeys(
            [*changed_normalized, *impacted_files]
        ))

        state["impact_radius"] = {
            "changed_nodes": len(ctx.get("changed_nodes", [])),
            "impacted_nodes": len(ctx.get("impacted_nodes", [])),
            "impacted_files": len(impacted_files),
            "database_id": database.database_id,
            "revision": database.revision,
        }
        return True

    except Exception as exc:
        state.setdefault("workflow_errors", []).append(
            {"source": "code_database_query", "message": f"代码数据库查询失败：{exc}"}
        )
        return False
