"""Node: 串行执行审查计划中的 Reviewer，收集候选 Finding。

Reviewer 输出首先视为候选 Finding，经过 FindingGate（app.engine.finding_gate）
过滤后写入 state.findings；质量指标由 app.engine.quality 计算，
Reviewer 失败降级为 workflow_errors，不中断整条流程。
"""

from __future__ import annotations

from app.engine.state import ReviewState
from app.engine.reviewers import REVIEWER_REGISTRY, ReviewerContext
from app.engine.context import select_reviewer_context
from app.engine.errors import format_user_error
from app.engine.finding_gate import filter_findings
from app.engine.quality import compute_quality_metrics, build_quality_checks


def run_reviews_node(state: ReviewState) -> ReviewState:
    all_findings = list(state.get("validator_findings", []))
    workflow_errors = list(state.get("workflow_errors", []))
    reviewer_outputs = dict(state.get("reviewer_outputs", {}))
    for reviewer_name in state.get("review_plan", []):
        reviewer = REVIEWER_REGISTRY.get(reviewer_name)
        if reviewer:
            trace = {
                "attempts": [],
                "candidate_findings": [],
                "error_message": None,
            }

            def capture_output(stage: str, output: str) -> None:
                max_chars = 20000
                trace["attempts"].append(
                    {
                        "stage": stage,
                        "output": output[:max_chars],
                        "truncated": len(output) > max_chars,
                    }
                )

            def capture_output_metadata(stage: str, metadata: dict) -> None:
                if not isinstance(metadata, dict):
                    return
                for attempt in reversed(trace["attempts"]):
                    if attempt.get("stage") != stage:
                        continue
                    finish_reason = metadata.get("finish_reason")
                    if finish_reason is not None:
                        attempt["finish_reason"] = finish_reason
                    if metadata.get("usage"):
                        attempt["usage"] = metadata["usage"]
                    if finish_reason == "length":
                        attempt["truncated"] = True
                    break

            try:
                if hook := state.get("_log_hook"):
                    hook(step="run_reviews", level="info",
                         message=f"正在执行 {reviewer_name}...")
                context = ReviewerContext(
                    diff=state.get("raw_diff", ""),
                    changed_files=state.get("changed_files", []),
                    file_context=select_reviewer_context(
                        state.get("file_context_cache", {}),
                        state.get("changed_files", []),
                        reviewer_name,
                    ),
                    repo_root=state.get("repo_id", "."),
                    revision=state.get("snapshot_revision", ""),
                    log_hook=state.get("_log_hook"),
                    output_hook=capture_output,
                    output_metadata_hook=capture_output_metadata,
                )
                findings = reviewer.review(context)
                trace["candidate_findings"] = findings
                all_findings.extend(findings)
            except Exception as e:
                user_message = format_user_error(e)
                error = {"reviewer": reviewer_name, "message": user_message}
                workflow_errors.append(error)
                trace["error_message"] = user_message
                if hook := state.get("_log_hook"):
                    hook(
                        step="run_reviews",
                        level="error",
                        message=f"{reviewer_name} 执行失败：{user_message}",
                    )
            reviewer_outputs[reviewer_name] = trace

    state["workflow_errors"] = workflow_errors
    state["reviewer_outputs"] = reviewer_outputs

    accepted_findings = filter_findings(
        all_findings,
        state.get("changed_files", []),
        state.get("raw_diff", ""),
    )
    metrics = compute_quality_metrics(all_findings, accepted_findings, reviewer_outputs)
    state["quality_metrics"] = metrics

    checks = list(state.get("checks", []))
    for error in workflow_errors:
        checks.append(
            {
                "name": f"reviewer_{error['reviewer']}",
                "status": "error",
                "message": error["message"],
            }
        )
    checks.extend(build_quality_checks(metrics))
    state["checks"] = checks
    state["findings"] = accepted_findings
    return state
