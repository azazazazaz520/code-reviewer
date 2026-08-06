"""code-review-graph（CRG）集成。

封装图谱构建与影响半径分析；任何失败都静默降级为普通文件上下文，
不中断审查流程。该模块不包含 LLM 逻辑，只负责结构性分析。
"""

from __future__ import annotations

from pathlib import Path

from app.engine.state import ReviewState


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
    try:
        from code_review_graph.tools.review import get_review_context
        from code_review_graph.tools.build import build_or_update_graph
    except ImportError:
        return False

    # 图谱生命周期：如果 .code-review-graph/ 不存在，自动构建
    crg_dir = Path(repo_path) / ".code-review-graph"
    if not crg_dir.exists():
        try:
            build_or_update_graph(full_rebuild=True, repo_root=repo_path)
        except Exception:
            return False

    try:
        result = get_review_context(
            changed_files=changed_files if changed_files else None,
            max_depth=2,
            include_source=True,
            max_lines_per_file=200,
            repo_root=repo_path,
            detail_level="standard",
        )
        if result.get("status") != "ok":
            return False

        ctx = result.get("context", {})
        impacted_files = ctx.get("impacted_files", [])
        state["context_candidates"] = list(dict.fromkeys(changed_files + impacted_files))

        state["impact_radius"] = {
            "changed_nodes": len(ctx.get("changed_nodes", [])),
            "impacted_nodes": len(ctx.get("impacted_nodes", [])),
            "impacted_files": len(impacted_files),
        }
        return True

    except ImportError:
        return False
    except Exception:
        return False
