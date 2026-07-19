"""CRG Tools — code-review-graph 集成。

通过 @register_tool 注册，供 Reviewer 和 Workflow Node 调用。
"""

from __future__ import annotations

from app.engine.tools.registry import register_tool


@register_tool(name="GetReviewContext", toolset="file")
def get_review_context(
    repo_root: str,
    changed_files: str = "",
    max_depth: int = 2,
) -> str:
    """获取变更文件的爆炸半径 + 源码片段 (code-review-graph)。

    Args:
        repo_root: 仓库根目录路径
        changed_files: 逗号分隔的变更文件列表（为空时自动从 git diff 检测）
        max_depth: 影响半径深度（默认 2）
    """
    try:
        from code_review_graph.tools.review import get_review_context as crg_review

        files_list = (
            [f.strip() for f in changed_files.split(",") if f.strip()]
            if changed_files
            else None
        )
        result = crg_review(
            changed_files=files_list,
            max_depth=max_depth,
            include_source=True,
            repo_root=repo_root,
            detail_level="standard",
        )
        # 精简输出：只返回关键字段
        ctx = result.get("context", {})
        return str({
            "status": result.get("status"),
            "summary": result.get("summary"),
            "impacted_files": ctx.get("impacted_files", [])[:30],
            "changed_nodes_count": len(ctx.get("changed_nodes", [])),
            "impacted_nodes_count": len(ctx.get("impacted_nodes", [])),
        })
    except ImportError:
        return '{"error": "code-review-graph not installed. Run: pip install code-review-graph"}'
    except Exception as e:
        return str({"error": str(e)})


@register_tool(name="GetImpactRadius", toolset="file")
def get_impact_radius(
    repo_root: str,
    changed_files: str,
    max_depth: int = 2,
) -> str:
    """计算变更文件的爆炸半径——BFS 追踪所有受影响的文件。

    Args:
        repo_root: 仓库根目录路径
        changed_files: 逗号分隔的变更文件列表
        max_depth: 影响半径深度（默认 2）
    """
    try:
        from code_review_graph.graph import GraphStore
        from code_review_graph.tools._common import _get_store

        store, root = _get_store(repo_root)
        try:
            files_list = [f.strip() for f in changed_files.split(",") if f.strip()]
            impact = store.get_impact_radius(files_list, max_depth=max_depth)
            return str({
                "impacted_files": impact.get("impacted_files", [])[:30],
                "changed_nodes": len(impact.get("changed_nodes", [])),
                "impacted_nodes": len(impact.get("impacted_nodes", [])),
                "truncated": impact.get("truncated", False),
            })
        finally:
            store.close()
    except ImportError:
        return '{"error": "code-review-graph not installed"}'
    except Exception as e:
        return str({"error": str(e)})
