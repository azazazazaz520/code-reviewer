"""Review Report 聚合。

把 severity 统计、风险等级推导、审查状态与最终 report 结构集中为纯函数，
generate_report 节点只负责把结果写回 ReviewState。前端契约字段与
backend/app/models/schemas.py 中的 ReviewReportResponse / ReviewChanges 保持一致。
"""

from __future__ import annotations

from app.engine.state import ReviewState


def count_by_severity(findings: list[dict]) -> dict[str, int]:
    """按严重级别统计 Finding 数量，未知级别按原样计数。"""
    severity_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for finding in findings:
        severity = finding.get("severity", "low")
        severity_count[severity] = severity_count.get(severity, 0) + 1
    return severity_count


def derive_risk(severity_count: dict[str, int]) -> str:
    """按最高严重级别推导风险等级，与前端 risk 徽章映射一致。"""
    if severity_count.get("critical", 0) > 0:
        return "critical"
    if severity_count.get("high", 0) > 0:
        return "high"
    if severity_count.get("medium", 0) > 0:
        return "medium"
    return "low"


def derive_review_status(workflow_errors: list, quality: dict) -> str:
    """审查状态：未完成数据库、输入覆盖或输出验证时标记 degraded。"""
    if workflow_errors or quality.get("truncated_outputs", 0) > 0:
        return "degraded"
    if quality.get("truncated_inputs", 0) > 0:
        return "degraded"
    if quality.get("tool_errors", 0) > 0 or quality.get("tool_budget_exhausted"):
        return "degraded"
    if quality.get("budget_exhausted") or quality.get("cancel_requested"):
        return "degraded"
    if quality.get(
        "pending_reviewer_assignments",
        quality.get("pending_assignments", 0),
    ) > 0:
        return "degraded"
    if quality.get("uncovered_files") or quality.get("uncovered_hunks"):
        return "degraded"
    if quality.get("coverage_status") not in {None, "complete"}:
        return "degraded"
    if quality.get("database_status") not in {None, "ready"}:
        return "degraded"
    if quality.get("extraction_status") not in {None, "complete"}:
        return "degraded"
    return "complete"


def build_summary(total: int, high_count: int) -> str:
    summary = f"本次审查发现 {total} 个问题"
    if high_count > 0:
        summary += f"（{high_count} 个高危）"
    return summary


def build_report(state: ReviewState) -> dict:
    """聚合最终 Review Report，不修改 state。"""
    findings = state.get("findings", [])
    severity_count = count_by_severity(findings)
    risk_level = derive_risk(severity_count)
    quality = state.get("quality_metrics", {})
    review_status = derive_review_status(state.get("workflow_errors", []), quality)
    total = len(findings)
    high_count = severity_count.get("high", 0)

    impacted_files = set(f.get("file", "") for f in findings if f.get("file"))
    test_gaps = len([
        f for f in findings
        if "test" in f.get("title", "").lower() or "测试" in f.get("title", "")
    ])

    return {
        "summary": build_summary(total, high_count),
        "risk_level": risk_level,
        "review_status": review_status,
        "findings": findings,
        "checks": state.get("checks", []),
        "quality": quality,
        "reviewer_outputs": state.get("reviewer_outputs", {}),
        "code_database": state.get("code_database_info", {}),
        "changes": {
            "review_type": state.get("review_type", ""),
            "source_type": state.get("source_type"),
            "pr_number": state.get("pr_number"),
            "commit_hash": state.get("commit_hash"),
            "branch": state.get("branch"),
            "base_branch": state.get("base_branch"),
            "base_revision": state.get("snapshot_base_revision"),
            "head_revision": state.get("snapshot_revision"),
            "workspace_fingerprint": state.get("workspace_fingerprint"),
            "workspace_stats": state.get("workspace_stats"),
            "changed_files": state.get("changed_files", []),
            "diff": state.get("raw_diff", ""),
        },
        "stats": {
            "total_findings": total,
            "by_severity": severity_count,
            "impacted_files": len(impacted_files),
            "test_gaps": test_gaps,
        },
    }
