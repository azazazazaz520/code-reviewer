"""CRG Tools — code-review-graph 集成。

通过 @register_tool 注册，供 Reviewer 和 Workflow Node 调用。
"""

from __future__ import annotations

from app.engine.paths import PathSecurityError, relative_snapshot_path
from app.engine.tools.registry import register_tool


def _normalise_file_list(repo_root: str, paths: list[str]) -> list[str]:
    """将图谱 Tool 的文件参数和结果统一为快照内相对路径。"""
    normalised: list[str] = []
    for path in paths:
        try:
            value = relative_snapshot_path(repo_root, path)
        except PathSecurityError:
            continue
        if value not in normalised:
            normalised.append(value)
    return normalised


def _normalise_single_file_path(repo_root: str, path: str) -> str:
    try:
        return relative_snapshot_path(repo_root, path)
    except PathSecurityError:
        return "<invalid-path>"


def _normalise_graph_paths(repo_root: str, value):
    """递归清理图谱结果中的文件路径，避免绝对快照路径进入模型上下文。"""
    if isinstance(value, dict):
        return {
            key: _normalise_single_file_path(repo_root, item)
            if key in {"file", "file_path", "filename"} and isinstance(item, str)
            else _normalise_graph_paths(repo_root, item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalise_graph_paths(repo_root, item) for item in value]
    return value


@register_tool(name="GetReviewContext", toolset="file")
def get_review_context(
    repo_root: str,
    changed_files: str = "",
    max_depth: int = 2,
) -> str:
    """获取变更文件的爆炸半径 + 源码片段 (code-review-graph)。"""
    try:
        from code_review_graph.tools.review import get_review_context as crg_review

        files_list = (
            _normalise_file_list(
                repo_root,
                [f.strip() for f in changed_files.split(",") if f.strip()],
            )
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
        ctx = result.get("context", {})
        return str({
            "status": result.get("status"),
            "summary": result.get("summary"),
            "impacted_files": _normalise_file_list(
                repo_root,
                ctx.get("impacted_files", [])[:30],
            ),
            "changed_nodes_count": len(ctx.get("changed_nodes", [])),
            "impacted_nodes_count": len(ctx.get("impacted_nodes", [])),
        })
    except ImportError:
        return '{"error": "code-review-graph not installed"}'
    except Exception as e:
        return str({"error": str(e)})


@register_tool(name="GetImpactRadius", toolset="file")
def get_impact_radius(
    repo_root: str,
    changed_files: str,
    max_depth: int = 2,
) -> str:
    """计算变更文件的爆炸半径——BFS 追踪所有受影响的文件。"""
    try:
        from code_review_graph.graph import GraphStore
        from code_review_graph.tools._common import _get_store

        store, root = _get_store(repo_root)
        try:
            files_list = _normalise_file_list(
                repo_root,
                [f.strip() for f in changed_files.split(",") if f.strip()],
            )
            impact = store.get_impact_radius(files_list, max_depth=max_depth)
            return str({
                "impacted_files": _normalise_file_list(
                    repo_root,
                    impact.get("impacted_files", [])[:30],
                ),
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


@register_tool(name="GetHubNodes", toolset="file")
def get_hub_nodes(repo_root: str, top_n: int = 10) -> str:
    """获取代码库中连接度最高的节点（架构热点）。"""
    try:
        from code_review_graph.tools.analysis_tools import get_hub_nodes_func
        result = _normalise_graph_paths(
            repo_root,
            get_hub_nodes_func(repo_root=repo_root, top_n=top_n),
        )
        return str(result)
    except ImportError:
        return '{"error": "code-review-graph not installed"}'
    except Exception as e:
        return str({"error": str(e)})


@register_tool(name="GetBridgeNodes", toolset="file")
def get_bridge_nodes(repo_root: str, top_n: int = 10) -> str:
    """获取架构咽喉节点（betweenness centrality 最高）。"""
    try:
        from code_review_graph.tools.analysis_tools import get_bridge_nodes_func
        result = _normalise_graph_paths(
            repo_root,
            get_bridge_nodes_func(repo_root=repo_root, top_n=top_n),
        )
        return str(result)
    except ImportError:
        return '{"error": "code-review-graph not installed"}'
    except Exception as e:
        return str({"error": str(e)})


@register_tool(name="GetSuggestedQuestions", toolset="file")
def get_suggested_questions(repo_root: str) -> str:
    """基于图谱分析自动生成审查问题。"""
    try:
        from code_review_graph.tools.analysis_tools import get_suggested_questions_func
        result = _normalise_graph_paths(
            repo_root,
            get_suggested_questions_func(repo_root=repo_root),
        )
        return str(result)
    except ImportError:
        return '{"error": "code-review-graph not installed"}'
    except Exception as e:
        return str({"error": str(e)})
