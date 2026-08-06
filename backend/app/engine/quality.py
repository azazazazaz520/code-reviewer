"""审查质量指标与质量门槛检查。

从候选 Finding 收敛过程的统计中生成 quality_metrics，并派生
finding_gate / finding_context 检查项。纯函数模块，可独立测试。
"""

from __future__ import annotations


def compute_quality_metrics(
    all_findings: list[dict],
    accepted_findings: list[dict],
    reviewer_outputs: dict[str, dict],
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
    return {
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
    return checks
