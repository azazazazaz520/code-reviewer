"""Review Workflow — 基于 LangGraph 的审查流程。

Load PR → Planning → Collect Context → Run Reviews → Reflection → Generate Report
                                    ↑                              │
                                    └── need_more_context ─────────┘
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Literal

from langgraph.graph import StateGraph, END

from app.config import settings
from app.engine.state import ReviewState
from app.engine.reviewers import REVIEWER_REGISTRY, ReviewerContext
from app.engine.tools.get_diff import get_diff, get_changed_files
from app.engine.tools.get_pr_diff import get_pr_diff, get_pr_changed_files
from app.engine.tools.read_file import read_file


# ─── LangGraph Nodes ──────────────────────────────────


def _load_pr_node(state: ReviewState) -> ReviewState:
    """Node 1: 加载 PR diff 和变更文件列表。

    PR 模式：从 GitHub API 获取 PR diff。
    Local 模式：从本地 git 获取 diff。
    """
    review_type = state.get("review_type", "local")
    repo_path = state.get("repo_id", ".")
    pr_number = state.get("pr_number")
    commit_hash = state.get("commit_hash")
    git_url = state.get("git_url", "")

    if hook := state.get("_log_hook"):
        hook(step="load_pr", level="info",
             message=f"正在获取代码变更... (type={review_type})")

    if review_type == "pr" and pr_number and git_url:
        # PR 模式：GitHub API
        diff_text = get_pr_diff(git_url, pr_number)
        files_text = get_pr_changed_files(git_url, pr_number)
        if diff_text.startswith("Error:") or files_text.startswith("Error:"):
            raise RuntimeError(diff_text if diff_text.startswith("Error:") else files_text)
    else:
        # Local 模式：本地 git
        base = commit_hash + "~1" if commit_hash else "HEAD~1"
        diff_text = get_diff(repo_path, base)
        if diff_text.startswith("Error: fatal:"):
            diff_text = get_diff(repo_path, "HEAD")
            files_text = get_changed_files(repo_path, "HEAD")
        else:
            files_text = get_changed_files(repo_path, base)

    state["raw_diff"] = diff_text
    state["changed_files"] = [
        f.strip() for f in files_text.split("\n")
        if f.strip() and not f.strip().startswith("Error:")
    ]

    if hook := state.get("_log_hook"):
        hook(step="load_pr", level="info",
             message=f"获取到 {len(state['changed_files'])} 个变更文件")

    return state


def _planning_node(state: ReviewState) -> ReviewState:
    """Node 2: 决定执行哪些 Reviewer。双层策略：
    - 软策略：文件类型规则
    - 硬触发器：安全关键词 + CRG 热点节点
    """
    plan = []
    changed = state.get("changed_files", [])
    diff = state.get("raw_diff", "")

    if hook := state.get("_log_hook"):
        hook(step="planning", level="info", message="正在规划审查策略...")

    # 文件类型规则
    if any(f.endswith(".py") or f.endswith(".js") or f.endswith(".ts") for f in changed):
        plan.append("style_reviewer")
    if any(f.endswith(".py") for f in changed):
        plan.append("performance_reviewer")

    # 安全关键词硬触发器
    security_keywords = ["sql", "password", "token", "secret", "pickle", "yaml.load",
                         "eval(", "exec(", "subprocess", "os.system", "shell=True"]
    if any(kw in diff.lower() for kw in security_keywords):
        plan.append("security_reviewer")

    # CRG 热点触发器：变更触及 hub 节点时强制激活 Security Reviewer
    if state.get("crg_enabled") and state.get("impact_radius"):
        impact = state["impact_radius"]
        if impact.get("impacted_nodes", 0) > 20 or impact.get("changed_nodes", 0) > 5:
            if "security_reviewer" not in plan:
                plan.append("security_reviewer")

    state["review_plan"] = plan if plan else ["style_reviewer"]

    if hook := state.get("_log_hook"):
        plan_str = ", ".join(state["review_plan"]) if state["review_plan"] else "(default style)"
        hook(step="planning", level="info",
             message=f"审查策略: {plan_str}")

    return state


def _collect_context_node(state: ReviewState) -> ReviewState:
    """Node 3: 收集变更文件内容到缓存。

    优先使用 CRG 爆炸半径分析（精准 ~15 个文件），
    降级为逐文件 ReadFile（最多 20 个）。
    """
    repo_path = state.get("repo_id", ".")
    changed_files = state.get("changed_files", [])
    cache: dict[str, str] = {}

    if hook := state.get("_log_hook"):
        hook(step="collect_context", level="info",
             message=f"正在收集文件上下文 ({len(state.get('changed_files', []))} 个文件)...")

    # 尝试 CRG 爆炸半径分析
    if _try_crg_context(state, repo_path, changed_files, cache):
        state["crg_enabled"] = True
        state["file_context_cache"] = cache

        source = "CRG" if state.get("crg_enabled") else "Normal"
        if hook := state.get("_log_hook"):
            hook(step="collect_context", level="info",
                 message=f"已收集 {len(cache)} 个文件 ({source})")

        return state

    # 降级：逐文件读取
    state["crg_enabled"] = False
    for file_path in changed_files[:20]:
        full_path = Path(repo_path) / file_path
        content = read_file(str(full_path), start_line=1, max_lines=200)
        cache[file_path] = content
    state["file_context_cache"] = cache

    source = "CRG" if state.get("crg_enabled") else "Normal"
    if hook := state.get("_log_hook"):
        hook(step="collect_context", level="info",
             message=f"已收集 {len(cache)} 个文件 ({source})")

    return state


def _try_crg_context(
    state: ReviewState, repo_path: str, changed_files: list[str], cache: dict[str, str]
) -> bool:
    """Try CRG blast-radius analysis. Returns True on success, False on any failure."""
    try:
        from code_review_graph.tools.review import get_review_context
        from code_review_graph.main import main as crg_build
    except ImportError:
        return False

    # 图谱生命周期：如果 .code-review-graph/ 不存在，自动构建
    crg_dir = Path(repo_path) / ".code-review-graph"
    if not crg_dir.exists():
        try:
            crg_build(["build"], standalone_mode=False)
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
        source_snippets = ctx.get("source_snippets", {})

        # 填充缓存：优先用 CRG 返回的源码片段，缺失的补读
        for fp in impacted_files[:20]:
            if fp in source_snippets:
                cache[fp] = source_snippets[fp]
            else:
                full_path = Path(repo_path) / fp
                cache[fp] = read_file(str(full_path), start_line=1, max_lines=200)

        # 确保原始变更文件也在缓存中
        for fp in changed_files:
            if fp not in cache:
                full_path = Path(repo_path) / fp
                cache[fp] = read_file(str(full_path), start_line=1, max_lines=200)

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


def _run_reviews_node(state: ReviewState) -> ReviewState:
    """Node 4: 并行执行所有 Reviewer，收集 Findings。"""
    context = ReviewerContext(
        diff=state.get("raw_diff", ""),
        changed_files=state.get("changed_files", []),
        file_context=state.get("file_context_cache", {}),
    )

    all_findings = []
    for reviewer_name in state.get("review_plan", []):
        reviewer = REVIEWER_REGISTRY.get(reviewer_name)
        if reviewer:
            try:
                if hook := state.get("_log_hook"):
                    hook(step="run_reviews", level="info",
                         message=f"正在执行 {reviewer_name}...")
                findings = reviewer.review(context)
                all_findings.extend(findings)
            except Exception as e:
                all_findings.append({
                    "severity": "low",
                    "file": "",
                    "line": 0,
                    "title": f"Reviewer '{reviewer_name}' 异常",
                    "reason": str(e),
                    "suggestion": "检查 Reviewer 实现或 LLM 配置",
                })

    state["findings"] = all_findings
    return state


def _reflection_node(state: ReviewState) -> ReviewState:
    """Node 5: 评估 Findings，决定是否需要更多上下文。

    判断标准（ADR 0001）:
      - 硬限制: reflection_round >= max_reflection_rounds → 停止
      - 软判断: 至少一个 finding 引用了具体行号 → 认为覆盖充分
    """
    if hook := state.get("_log_hook"):
        hook(step="reflection", level="info",
             message=f"反思中 (第 {state.get('reflection_round', 0) + 1}/{settings.max_reflection_rounds} 轮)...")

    state["reflection_round"] = state.get("reflection_round", 0) + 1
    max_rounds = settings.max_reflection_rounds

    findings = state.get("findings", [])
    has_line_refs = any(f.get("line", 0) > 0 for f in findings)

    if state["reflection_round"] >= max_rounds:
        state["need_more_context"] = False
    elif not has_line_refs and state["reflection_round"] < max_rounds:
        state["need_more_context"] = True
    else:
        state["need_more_context"] = False

    return state


def _should_retry(state: ReviewState) -> Literal["collect", "report"]:
    """条件边：是否需要回退到 Collect Context。"""
    return "collect" if state.get("need_more_context") else "report"


def _generate_report_node(state: ReviewState) -> ReviewState:
    """Node 6: 生成最终 Report。"""
    if hook := state.get("_log_hook"):
        hook(step="generate_report", level="info", message="正在生成审查报告...")

    findings = state.get("findings", [])

    severity_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low")
        severity_count[sev] = severity_count.get(sev, 0) + 1

    if severity_count["critical"] > 0:
        risk = "critical"
    elif severity_count["high"] > 0:
        risk = "high"
    elif severity_count["medium"] > 0:
        risk = "medium"
    else:
        risk = "low"

    impacted_files = set(f.get("file", "") for f in findings if f.get("file"))
    test_gaps = len([
        f for f in findings
        if "test" in f.get("title", "").lower() or "测试" in f.get("title", "")
    ])

    total = len(findings)
    high_count = severity_count.get("high", 0)
    summary = f"本次审查发现 {total} 个问题"
    if high_count > 0:
        summary += f"（{high_count} 个高危）"

    state["summary"] = summary
    state["risk_level"] = risk

    # 存储 report 到 state（供外部读取）
    state["report"] = {
        "summary": summary,
        "risk_level": risk,
        "findings": findings,
        "stats": {
            "total_findings": total,
            "by_severity": severity_count,
            "impacted_files": len(impacted_files),
            "test_gaps": test_gaps,
        },
    }
    return state


# ─── 构建 Graph ───────────────────────────────────────


def _build_graph() -> StateGraph:
    builder = StateGraph(ReviewState)

    builder.add_node("load_pr", _load_pr_node)
    builder.add_node("planning", _planning_node)
    builder.add_node("collect_context", _collect_context_node)
    builder.add_node("run_reviews", _run_reviews_node)
    builder.add_node("reflection", _reflection_node)
    builder.add_node("generate_report", _generate_report_node)

    builder.set_entry_point("load_pr")
    builder.add_edge("load_pr", "collect_context")
    builder.add_edge("collect_context", "planning")
    builder.add_edge("planning", "run_reviews")
    builder.add_edge("run_reviews", "reflection")

    builder.add_conditional_edges(
        "reflection",
        _should_retry,
        {"collect": "collect_context", "report": "generate_report"},
    )
    builder.add_edge("generate_report", END)

    return builder.compile()


_graph = _build_graph()


# ─── 公开入口 ─────────────────────────────────────────


def run_workflow(
    repo_path: str,
    git_url: str = "",
    review_type: str = "pr",
    pr_number: int | None = None,
    commit_hash: str | None = None,
    base_branch: str | None = None,
    log_hook: Callable | None = None,
) -> dict:
    """运行审查 Workflow，返回报告 dict。"""
    initial_state: ReviewState = {
        "repo_id": repo_path,
        "git_url": git_url,
        "review_type": review_type,
        "pr_number": pr_number,
        "commit_hash": commit_hash,
        "base_branch": base_branch,
        "raw_diff": "",
        "changed_files": [],
        "review_plan": [],
        "file_context_cache": {},
        "findings": [],
        "reflection_round": 0,
        "need_more_context": False,
        "summary": "",
        "risk_level": "low",
        "crg_enabled": True,
        "impact_radius": None,
        "_log_hook": log_hook,
    }

    final_state = _graph.invoke(initial_state)
    return final_state.get("report", {})
