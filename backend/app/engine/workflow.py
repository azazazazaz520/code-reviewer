"""Review Workflow — 基于 LangGraph 的审查流程。

Load PR → Planning → Collect Context → Run Reviews → Reflection → Generate Report
                                    ↑                              │
                                    └── need_more_context ─────────┘
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from langgraph.graph import StateGraph, END

from app.config import settings
from app.engine.state import ReviewState
from app.engine.reviewers.style import StyleReviewer
from app.engine.reviewers.security import SecurityReviewer
from app.engine.reviewers.base import ReviewerContext
from app.engine.tools.get_diff import get_diff, get_changed_files
from app.engine.tools.read_file import read_file


# ─── 审查器注册表 ──────────────────────────────────────

REVIEWER_REGISTRY = {
    "style_reviewer": StyleReviewer(),
    "security_reviewer": SecurityReviewer(),
}


# ─── LangGraph Nodes ──────────────────────────────────


def _load_pr_node(state: ReviewState) -> ReviewState:
    """Node 1: 加载 PR diff 和变更文件列表。"""
    repo_path = state.get("repo_id", ".")
    commit_hash = state.get("commit_hash")
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
    return state


def _planning_node(state: ReviewState) -> ReviewState:
    """Node 2: 决定执行哪些 Reviewer。"""
    plan = []
    changed = state.get("changed_files", [])
    diff = state.get("raw_diff", "")

    # 硬触发器：文件类型
    if any(f.endswith(".py") or f.endswith(".js") or f.endswith(".ts") for f in changed):
        plan.append("style_reviewer")

    # 硬触发器：安全关键词
    security_keywords = ["sql", "password", "token", "secret", "pickle", "yaml.load",
                         "eval(", "exec(", "subprocess", "os.system", "shell=True"]
    if any(kw in diff.lower() for kw in security_keywords):
        plan.append("security_reviewer")

    state["review_plan"] = plan if plan else ["style_reviewer"]
    return state


def _collect_context_node(state: ReviewState) -> ReviewState:
    """Node 3: 收集变更文件内容到缓存。

    后续可集成 CRG 爆炸半径分析来优化文件选择。
    """
    repo_path = state.get("repo_id", ".")
    cache: dict[str, str] = {}
    for file_path in state.get("changed_files", [])[:20]:  # 限制 20 个文件
        full_path = Path(repo_path) / file_path
        content = read_file(str(full_path), start_line=1, max_lines=200)
        cache[file_path] = content
    state["file_context_cache"] = cache
    return state


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
    builder.add_edge("load_pr", "planning")
    builder.add_edge("planning", "collect_context")
    builder.add_edge("collect_context", "run_reviews")
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
    review_type: str = "pr",
    pr_number: int | None = None,
    commit_hash: str | None = None,
    base_branch: str | None = None,
) -> dict:
    """运行审查 Workflow，返回报告 dict。"""
    initial_state: ReviewState = {
        "repo_id": repo_path,
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
        "crg_enabled": False,
        "impact_radius": None,
    }

    final_state = _graph.invoke(initial_state)
    return final_state.get("report", {})
