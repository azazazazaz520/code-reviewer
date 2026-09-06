"""审查质量指标与质量门槛检查。

从候选 Finding 收敛过程的统计中生成 quality_metrics，并派生
finding_gate / finding_context 检查项。纯函数模块，可独立测试。
"""

from __future__ import annotations


QUALITY_CHECK_NAMES = {
    "finding_gate",
    "finding_context",
    "review_coverage",
    "review_hunks",
    "review_assignment_coverage",
    "review_input_truncation",
    "context_collection",
    "review_tools",
    "review_tool_budget",
    "review_budget",
    "review_cancelled",
}


def compute_quality_metrics(
    all_findings: list[dict],
    accepted_findings: list[dict],
    reviewer_outputs: dict[str, dict],
    coverage: dict | None = None,
    *,
    rejection_reasons: dict[str, int] | None = None,
) -> dict:
    """统计候选 Finding 到最终 Finding 的收敛质量。

    参数：
      all_findings：所有 Reviewer 产出的候选 Finding（含确定性校验器）
      accepted_findings：通过 FindingGate 的 Finding
      reviewer_outputs：reviewer_name → trace（含 attempts 与截断标记）
    """
    context_finding_count = sum(
        finding.get("evidence_type") == "reviewer_context"
        for finding in accepted_findings
    )
    evidence_count = sum(
        finding.get("evidence_type") in {"static_check", "tool_verified"}
        for finding in accepted_findings
    )
    metrics = {
        "candidate_findings": len(all_findings),
        "accepted_findings": len(accepted_findings),
        "filtered_findings": len(all_findings) - len(accepted_findings),
        "located_findings": sum(
            finding.get("line", 0) > 0 for finding in accepted_findings
        ),
        "static_evidence_findings": evidence_count,
        "reviewer_context_findings": context_finding_count,
        "truncated_outputs": sum(
            attempt.get("truncated", False)
            for trace in reviewer_outputs.values()
            for attempt in trace.get("attempts", [])
        ),
    }
    if rejection_reasons is not None:
        metrics["filtered_reasons"] = dict(rejection_reasons)
    if coverage:
        metrics.update(coverage)
    return metrics


def build_quality_checks(metrics: dict) -> list[dict]:
    """由质量指标派生检查项，不修改已有 checks。"""
    checks: list[dict] = []
    filtered_count = metrics.get("filtered_findings", 0)
    if filtered_count:
        checks.append(
            {
                "name": "finding_gate",
                "status": "warning",
                "message": (
                    f"{filtered_count} 个候选 Finding 未通过证据门槛，"
                    "未计入最终结果。"
                ),
            }
        )
    context_finding_count = metrics.get("reviewer_context_findings", 0)
    if context_finding_count:
        checks.append(
            {
                "name": "finding_context",
                "status": "warning",
                "message": (
                    f"{context_finding_count} 个问题出现在修改文件的相邻代码中，"
                    "请确认是否由本次提交引起。"
                ),
            }
        )
    if metrics.get("uncovered_files"):
        checks.append(
            {
                "name": "review_coverage",
                "status": "warning",
                "message": (
                    f"仍有 {len(metrics['uncovered_files'])} 个文件未完成上下文读取。"
                ),
            }
        )
    if metrics.get("uncovered_hunks"):
        checks.append(
            {
                "name": "review_hunks",
                "status": "warning",
                "message": (
                    f"仍有 {len(metrics['uncovered_hunks'])} 个 Diff Hunk 未完成上下文覆盖。"
                ),
            }
        )
    pending_assignments = metrics.get(
        "pending_reviewer_assignments",
        metrics.get("pending_assignments", 0),
    )
    if pending_assignments:
        checks.append(
            {
                "name": "review_assignment_coverage",
                "status": "warning",
                "message": (
                    f"仍有 {pending_assignments} 个 Reviewer 分配待处理，"
                    "当前报告仅包含已完成的审查单元。"
                ),
            }
        )
    if metrics.get("truncated_inputs"):
        checks.append(
            {
                "name": "review_input_truncation",
                "status": "warning",
                "message": f"有 {metrics['truncated_inputs']} 个审查输入批次发生截断。",
            }
        )
    if metrics.get("context_errors"):
        checks.append(
            {
                "name": "context_collection",
                "status": "warning",
                "message": (
                    f"有 {len(metrics['context_errors'])} 个上下文读取失败，"
                    "相关文件未计入完整覆盖。"
                ),
            }
        )
    if metrics.get("tool_errors"):
        checks.append(
            {
                "name": "review_tools",
                "status": "warning",
                "message": f"Reviewer Tool 调用失败 {metrics['tool_errors']} 次。",
            }
        )
    if metrics.get("tool_budget_exhausted"):
        checks.append(
            {
                "name": "review_tool_budget",
                "status": "warning",
                "message": "部分审查单元已达到 Tool 调用预算，后续结论仅基于已取得的上下文。",
            }
        )
    if metrics.get("budget_exhausted"):
        reason = metrics.get("budget_exhausted_reason") or "unknown"
        checks.append(
            {
                "name": "review_budget",
                "status": "warning",
                "message": f"审查达到执行预算（{reason}），仍有部分审查单元未完成。",
            }
        )
    if metrics.get("cancel_requested"):
        checks.append(
            {
                "name": "review_cancelled",
                "status": "warning",
                "message": "审查任务已取消，报告仅包含取消前已完成的审查单元。",
            }
        )
    return checks


def merge_checks(existing: list[dict], updates: list[dict]) -> list[dict]:
    """按检查项名称更新状态，保留未参与本轮计算的检查项。"""
    updates_by_name: dict[str, dict] = {}
    unnamed_updates: list[dict] = []
    for check in updates:
        name = check.get("name")
        if name:
            updates_by_name[name] = check
        else:
            unnamed_updates.append(check)
    update_names = set(updates_by_name) | QUALITY_CHECK_NAMES
    merged = [
        check for check in existing
        if check.get("name") not in update_names
    ]
    merged.extend(updates_by_name.values())
    merged.extend(unnamed_updates)
    return merged
