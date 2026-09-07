"""Node: 串行执行审查计划中的 Reviewer，收集候选 Finding。

Reviewer 输出首先视为候选 Finding，经过 FindingGate（app.engine.finding_gate）
过滤后写入 state.findings；质量指标由 app.engine.quality 计算，
Reviewer 失败降级为 workflow_errors，不中断整条流程。
"""

from __future__ import annotations

import json
from typing import Iterable

from app.config import settings
from app.engine.state import ReviewState
from app.engine.llm import LLM_USAGE_METRIC_FIELDS
from app.engine.reviewers import REVIEWER_REGISTRY, ReviewerContext
from app.engine.context import select_reviewer_batch_context
from app.engine.errors import format_user_error
from app.engine.execution import (
    ReviewBudgetExceeded,
    ReviewCancelled,
    get_or_create_budget,
)
from app.engine.finding_gate import filter_findings
from app.engine.quality import compute_quality_metrics, build_quality_checks, merge_checks
from app.engine.review_units import (
    build_review_units,
    build_reviewer_batches,
    reviewer_handles_file,
)
from app.engine.tools.context import TaskToolCache


def _finding_key(finding: dict) -> str:
    """为跨批次 Finding 生成稳定键，避免重复审查结果反复进入报告。"""
    return json.dumps(finding, ensure_ascii=False, sort_keys=True, default=str)


def _append_unique_findings(target: list[dict], findings: list[dict]) -> None:
    seen = {_finding_key(finding) for finding in target}
    for finding in findings:
        key = _finding_key(finding)
        if key not in seen:
            target.append(finding)
            seen.add(key)


def _add_workflow_error(errors: list[dict], error: dict) -> None:
    key = (
        error.get("reviewer"),
        error.get("source"),
        error.get("message"),
    )
    if not any(
        (item.get("reviewer"), item.get("source"), item.get("message")) == key
        for item in errors
    ):
        errors.append(error)


def _iter_review_assignments(state: ReviewState, reviewer_name: str) -> Iterable[tuple[dict, object]]:
    """生成 Reviewer 批次及其确定性上下文。"""
    units = state.get("review_units", [])
    if not units:
        units = build_review_units(
            state.get("raw_diff", ""),
            state.get("changed_files", []),
            state.get("snapshot_revision", ""),
            context_candidates=state.get("context_candidates", []),
            file_context=state.get("file_context_cache", {}),
        )
        state["review_units"] = units

    for batch in build_reviewer_batches(units, reviewer_name):
        yield batch, select_reviewer_batch_context(
            state.get("file_context_cache", {}),
            batch,
            reviewer_name,
        )


def _cancel_check(state: ReviewState):
    callback = state.get("_cancel_check")
    return callback if callable(callback) else None


def _sync_budget_state(
    state: ReviewState,
    budget,
    pending_units: int,
    *,
    planned_assignments: int = 0,
    pending_assignments: int = 0,
    pending_unit_ids: list[str] | None = None,
) -> None:
    state["review_budget"] = {
        **budget.as_dict(
            planned_units=len(state.get("review_units", [])),
            pending_units=pending_units,
            planned_assignments=planned_assignments,
            pending_assignments=pending_assignments,
            pending_unit_ids=pending_unit_ids,
        ),
        "max_review_duration_seconds": budget.max_duration_seconds,
        "started_at": budget.started_at,
    }


def _merge_input_coverage(target: dict, incoming: dict) -> None:
    """合并同一 Reviewer 的批次覆盖信息，避免后一个批次覆盖前面的证据。"""
    if not isinstance(incoming, dict):
        return

    truncation_events = list(dict.fromkeys(
        [
            *(
                event for event in target.get("truncation_events", [])
                if isinstance(event, str) and event
            ),
            *(
                event for event in incoming.get("truncation_events", [])
                if isinstance(event, str) and event
            ),
        ]
    ))
    context_limit_events = list(dict.fromkeys(
        [
            *(
                event for event in target.get("context_limit_events", [])
                if isinstance(event, str) and event
            ),
            *(
                event for event in incoming.get("context_limit_events", [])
                if isinstance(event, str) and event
            ),
        ]
    ))
    omitted_files = list(dict.fromkeys(
        [
            *(
                path for path in target.get("omitted_files", [])
                if isinstance(path, str) and path
            ),
            *(
                path for path in incoming.get("omitted_files", [])
                if isinstance(path, str) and path
            ),
        ]
    ))
    context_request_failure_events: dict[str, dict] = {}
    for event in [
        *target.get("context_request_failure_events", []),
        *incoming.get("context_request_failure_events", []),
    ]:
        if isinstance(event, dict):
            key = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
            context_request_failure_events[key] = event
    llm_usage_events = [
        event
        for event in [
            *target.get("llm_usage_events", []),
            *incoming.get("llm_usage_events", []),
        ]
        if isinstance(event, dict)
    ]

    target.update(
        {
            "truncation_events": truncation_events,
            "critical_truncation_events": truncation_events,
            "truncated_inputs": len(truncation_events),
            "critical_truncated_inputs": len(truncation_events),
            "context_limit_events": context_limit_events,
            "context_limited_inputs": len(context_limit_events),
            "omitted_files": omitted_files,
            "context_request_failure_events": list(
                context_request_failure_events.values()
            ),
            "llm_usage_events": llm_usage_events,
        }
    )

    for key, value in incoming.items():
        if key not in {
            "truncation_events",
            "truncated_inputs",
            "critical_truncation_events",
            "critical_truncated_inputs",
            "context_limit_events",
            "context_limited_inputs",
            "omitted_files",
            "context_request_failure_events",
            "llm_usage_events",
        }:
            if key in {
                "provider_requests",
                "session_rebuilds",
                "context_requests",
                "context_reads",
                "context_cache_hits",
                "context_request_failures",
                "output_repair_failures",
                *LLM_USAGE_METRIC_FIELDS.values(),
            }:
                target[key] = target.get(key, 0) + value
            else:
                target[key] = value


def _aggregate_llm_usage(reviewer_outputs: dict[str, dict]) -> dict[str, int | float]:
    """从各 Reviewer trace 汇总实际 Provider 请求的模型 token。"""
    metric_keys = ("provider_requests", *LLM_USAGE_METRIC_FIELDS.values())
    totals = {key: 0 for key in metric_keys}
    for trace in reviewer_outputs.values():
        input_coverage = trace.get("input_coverage", {})
        if not isinstance(input_coverage, dict):
            continue
        for key in metric_keys:
            value = input_coverage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value

    prompt_tokens = totals["llm_prompt_tokens"]
    if prompt_tokens <= 0:
        return {}

    cache_tokens = (
        totals["llm_prompt_cache_hit_tokens"]
        + totals["llm_prompt_cache_miss_tokens"]
    )
    totals["llm_prompt_cache_hit_rate"] = (
        totals["llm_prompt_cache_hit_tokens"] / cache_tokens
        if cache_tokens > 0
        else 0.0
    )
    return totals


def _aggregate_review_diagnostics(reviewer_outputs: dict[str, dict]) -> dict:
    """汇总批次级上下文请求与结构化输出修复结果。"""
    count_fields = (
        "context_requests",
        "context_request_failures",
        "output_repair_failures",
    )
    totals = {key: 0 for key in count_fields}
    failure_events: list[dict] = []
    for trace in reviewer_outputs.values():
        input_coverage = trace.get("input_coverage", {})
        for key in count_fields:
            totals[key] += int(input_coverage.get(key, 0) or 0)
        for event in input_coverage.get("context_request_failure_events", []):
            if isinstance(event, dict) and event not in failure_events:
                failure_events.append(event)
    totals["context_request_failure_events"] = failure_events
    return totals


def _execute_reviewer_group(
    reviewer_name: str,
    reviewer,
    assignments: list[tuple[dict, object]],
    previous_trace: dict,
    state: ReviewState,
    tool_cache: TaskToolCache,
    cancel_check,
    budget,
) -> dict:
    """串行执行同一 Reviewer 的批次，不保留跨批次消息历史。"""
    trace = {
        "attempts": list(previous_trace.get("attempts", [])),
        "candidate_findings": list(previous_trace.get("candidate_findings", [])),
        "input_coverage": dict(previous_trace.get("input_coverage", {})),
        "error_message": previous_trace.get("error_message"),
    }
    findings: list[dict] = []
    errors: list[dict] = []
    cancelled = False
    budget_exhausted = False
    completed_count = 0
    completed_unit_ids: set[str] = set()
    completed_batch_ids: set[str] = set()
    attempted_unit_ids: set[str] = set()
    current_batch_id = ""
    previous_coverage = previous_trace.get("input_coverage", {})
    llm_usage_state = {
        "provider_requests": (
            previous_coverage.get("provider_requests", 0)
            if isinstance(previous_coverage, dict)
            else 0
        )
    }
    def capture_output(stage: str, output: str) -> None:
        max_chars = 20000
        trace["attempts"].append(
            {
                "batch_id": current_batch_id,
                "unit_id": current_batch_id,
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
            for key in ("max_tokens", "thinking"):
                if metadata.get(key) is not None:
                    attempt[key] = metadata[key]
            if "truncated" in metadata:
                attempt["truncated"] = bool(metadata["truncated"])
            elif finish_reason == "length":
                attempt["truncated"] = True
            break

    for batch, selection in assignments:
        batch_id = batch.get("batch_id", "")
        current_batch_id = batch_id
        try:
            # 主模型调用在真正开始 Reviewer 前原子预留，避免并行调度时
            # 先预留整批调用而把已排队任务误判为超出预算。
            budget.reserve_primary_call(cancel_check)
        except ReviewCancelled:
            cancelled = True
            break
        except ReviewBudgetExceeded:
            budget_exhausted = True
            break
        context = ReviewerContext(
            diff=batch.get("diff", ""),
            changed_files=list(batch.get("primary_files", [])),
            task_changed_files=list(state.get("changed_files", [])),
            file_context=selection.files,
            shared_file_context={},
            task_id=state.get("task_id", ""),
            reviewer_name=reviewer_name,
            review_scope=(
                dict(state.get("review_scope"))
                if isinstance(state.get("review_scope"), dict)
                else {}
            ),
            llm_usage_state=llm_usage_state,
            repo_root=state.get("repo_id", "."),
            revision=state.get("snapshot_revision", ""),
            tool_context=state.get("tool_context"),
            tool_cache=tool_cache,
            input_coverage={
                "truncated_inputs": selection.truncated_inputs,
                "critical_truncated_inputs": selection.truncated_inputs,
                "truncation_events": list(selection.truncation_events),
                "critical_truncation_events": list(selection.truncation_events),
                "context_limited_inputs": len(selection.context_limit_events),
                "context_limit_events": list(selection.context_limit_events),
                "context_request_failure_events": [],
                "omitted_files": list(selection.omitted_files),
                "batch_id": batch_id,
                "unit_id": batch_id,
                "unit_ids": list(batch.get("unit_ids", [])),
                "hunk_ids": list(batch.get("hunk_ids", [])),
            },
            log_hook=state.get("_log_hook"),
            output_hook=capture_output,
            output_metadata_hook=capture_output_metadata,
            cancel_check=cancel_check,
        )
        try:
            if hook := state.get("_log_hook"):
                hook(
                    step="run_reviews",
                    level="info",
                    message=(
                        f"正在执行 {reviewer_name}（Reviewer 批次 "
                        f"{batch_id[:12]}）..."
                    ),
                )
            attempted_unit_ids.add(batch_id)
            unit_findings = reviewer.review(context)
            _append_unique_findings(trace["candidate_findings"], unit_findings)
            _append_unique_findings(findings, unit_findings)
            completed_count += 1
            completed_batch_ids.add(batch_id)
            completed_unit_ids.update(batch.get("unit_ids", []))
        except ReviewCancelled:
            cancelled = True
            break
        except Exception as exc:
            user_message = format_user_error(exc)
            error = {"reviewer": reviewer_name, "message": user_message}
            _add_workflow_error(errors, error)
            trace["error_message"] = user_message
            if hook := state.get("_log_hook"):
                hook(
                    step="run_reviews",
                    level="error",
                    message=f"{reviewer_name} 执行失败：{user_message}",
                )
        finally:
            _merge_input_coverage(trace["input_coverage"], context.input_coverage)

    return {
        "trace": trace,
        "findings": findings,
        "errors": errors,
        "cancelled": cancelled,
        "budget_exhausted": budget_exhausted,
        "completed_count": completed_count,
        "completed_unit_ids": sorted(completed_unit_ids),
        "completed_batch_ids": sorted(completed_batch_ids),
        "attempted_unit_ids": sorted(attempted_unit_ids),
    }


def run_reviews_node(state: ReviewState) -> ReviewState:
    all_findings = [
        {**finding, "_evidence_source": "validator"}
        for finding in state.get("validator_findings", [])
    ]
    _append_unique_findings(all_findings, state.get("candidate_findings", []))
    new_candidate_findings: list[dict] = []
    workflow_errors: list[dict] = []
    for error in state.get("workflow_errors", []):
        _add_workflow_error(workflow_errors, error)
    reviewer_outputs = dict(state.get("reviewer_outputs", {}))
    coverage = dict(state.get("coverage", {}))
    truncation_events = set(coverage.get("truncation_events", []))
    critical_truncation_events = set(
        coverage.get("critical_truncation_events", truncation_events)
    )
    context_limit_events = set(coverage.get("context_limit_events", []))
    legacy_truncated_inputs = coverage.get("truncated_inputs", 0)
    reviewed_unit_keys = {
        name: set(keys)
        for name, keys in state.get("reviewed_unit_keys", {}).items()
    }
    completed_batch_keys = {
        name: set(keys)
        for name, keys in state.get("completed_batch_keys", {}).items()
    }
    budget = get_or_create_budget(
        state,
        max_duration_seconds=settings.max_review_duration_seconds,
    )
    tool_cache = state.get("tool_cache")
    if not isinstance(tool_cache, TaskToolCache):
        tool_cache = TaskToolCache()
        state["tool_cache"] = tool_cache
    cancel_check = _cancel_check(state)
    if not state.get("review_units"):
        state["review_units"] = build_review_units(
            state.get("raw_diff", ""),
            state.get("changed_files", []),
            state.get("snapshot_revision", ""),
            context_candidates=state.get("context_candidates", []),
            file_context=state.get("file_context_cache", {}),
        )
    eligible_unit_ids = {
        unit.get("unit_id", "")
        for reviewer_name in state.get("review_plan", [])
        for unit in state.get("review_units", [])
        if reviewer_name in REVIEWER_REGISTRY
        and reviewer_handles_file(reviewer_name, unit.get("primary_file", ""))
    }
    assignments_by_reviewer: dict[str, list[tuple[dict, object]]] = {}
    planned_batch_ids: dict[str, set[str]] = {}
    review_batches: dict[str, list[dict]] = {}
    for reviewer_name in state.get("review_plan", []):
        reviewer = REVIEWER_REGISTRY.get(reviewer_name)
        if not reviewer:
            message = f"审查计划中的 Reviewer 不可用：{reviewer_name}"
            _add_workflow_error(workflow_errors, {"reviewer": reviewer_name, "message": message})
            reviewer_outputs[reviewer_name] = {
                "attempts": [],
                "candidate_findings": [],
                "input_coverage": {},
                "error_message": message,
            }
            continue

        reviewer_unit_keys = reviewed_unit_keys.setdefault(reviewer_name, set())
        assignments: list[tuple[dict, object]] = []
        all_assignments = list(_iter_review_assignments(state, reviewer_name))
        review_batches[reviewer_name] = [batch for batch, _ in all_assignments]
        planned_batch_ids[reviewer_name] = {
            batch.get("batch_id", "") for batch, _ in all_assignments
        }
        for batch, selection in all_assignments:
            batch_id = batch.get("batch_id", "")
            if batch_id in reviewer_unit_keys:
                continue
            assignments.append((batch, selection))
        if assignments:
            assignments_by_reviewer[reviewer_name] = assignments
        if state.get("cancel_requested") or budget.exhausted_reason:
            break

    state["review_batches"] = review_batches
    planned_assignments = sum(len(ids) for ids in planned_batch_ids.values())

    reviewer_names = [
        name for name in state.get("review_plan", [])
        if name in assignments_by_reviewer
    ]
    if hook := state.get("_log_hook"):
        hook(
            step="run_reviews",
            level="info",
            message=(
                f"审查调度：{len(state.get('review_units', []))} 个 ReviewUnit 合并为 "
                f"{planned_assignments} 个 Reviewer 批次"
            ),
        )
    results: dict[str, dict] = {}
    if settings.review_parallelism > 1 and len(reviewer_names) > 1:
        from concurrent.futures import ThreadPoolExecutor

        worker_count = min(settings.review_parallelism, len(reviewer_names))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="reviewer") as executor:
            futures = {
                name: executor.submit(
                    _execute_reviewer_group,
                    name,
                    REVIEWER_REGISTRY[name],
                    assignments_by_reviewer[name],
                    reviewer_outputs.get(name, {}),
                    state,
                    tool_cache,
                    cancel_check,
                    budget,
                )
                for name in reviewer_names
            }
            results = {name: futures[name].result() for name in reviewer_names}
    else:
        results = {
            name: _execute_reviewer_group(
                name,
                REVIEWER_REGISTRY[name],
                assignments_by_reviewer[name],
                reviewer_outputs.get(name, {}),
                state,
                tool_cache,
                cancel_check,
                budget,
            )
            for name in reviewer_names
        }

    completed_batch_ids_by_reviewer: dict[str, set[str]] = {
        name: set(keys) for name, keys in completed_batch_keys.items()
    }
    for reviewer_name in state.get("review_plan", []):
        result = results.get(reviewer_name)
        if not result:
            continue
        reviewer_outputs[reviewer_name] = result["trace"]
        reviewed_unit_keys.setdefault(reviewer_name, set()).update(
            result["attempted_unit_ids"]
        )
        budget.completed_assignments += result["completed_count"]
        completed_batch_ids_by_reviewer.setdefault(reviewer_name, set()).update(
            result["completed_batch_ids"]
        )
        completed_unit_ids = set(state.get("completed_unit_ids", []))
        completed_unit_ids.update(result["completed_unit_ids"])
        state["completed_unit_ids"] = sorted(completed_unit_ids)
        for error in result["errors"]:
            _add_workflow_error(workflow_errors, error)
        for finding in result["findings"]:
            tagged = {**finding, "_evidence_source": "reviewer"}
            _append_unique_findings(new_candidate_findings, [tagged])
            _append_unique_findings(all_findings, [tagged])
        input_coverage = result["trace"].get("input_coverage", {})
        truncation_events.update(input_coverage.get("truncation_events", []))
        critical_truncation_events.update(
            input_coverage.get(
                "critical_truncation_events",
                input_coverage.get("truncation_events", []),
            )
        )
        context_limit_events.update(input_coverage.get("context_limit_events", []))
        if result["cancelled"]:
            state["cancel_requested"] = True

    state["workflow_errors"] = workflow_errors
    state["reviewer_outputs"] = reviewer_outputs
    candidate_findings = list(state.get("candidate_findings", []))
    _append_unique_findings(candidate_findings, new_candidate_findings)
    state["candidate_findings"] = candidate_findings
    state["reviewed_unit_keys"] = {
        name: sorted(keys) for name, keys in reviewed_unit_keys.items()
    }
    # 保留旧字段的读取兼容性，历史调用方仍可以看到已完成单元标识。
    state["reviewed_batch_keys"] = dict(state["reviewed_unit_keys"])
    state["completed_batch_keys"] = {
        name: sorted(keys)
        for name, keys in completed_batch_ids_by_reviewer.items()
    }
    tool_stats = tool_cache.stats()
    budget.completed_units = len(state.get("completed_unit_ids", []))
    budget.context_read_requests = tool_stats["context_read_requests"]
    budget.context_cache_hits = tool_stats["context_cache_hits"]
    budget.context_cache_misses = tool_stats["context_cache_misses"]
    completed_assignments = sum(
        len(ids) for ids in completed_batch_ids_by_reviewer.values()
    )
    pending_assignments = max(0, planned_assignments - completed_assignments)
    completed_unit_ids = set(state.get("completed_unit_ids", []))
    pending_units = len(eligible_unit_ids - completed_unit_ids)
    pending_unit_ids = sorted(eligible_unit_ids - completed_unit_ids)
    state["pending_unit_ids"] = pending_unit_ids
    _sync_budget_state(
        state,
        budget,
        pending_units,
        planned_assignments=planned_assignments,
        pending_assignments=pending_assignments,
        pending_unit_ids=pending_unit_ids,
    )
    if hook := state.get("_log_hook"):
        hook(
            step="run_reviews",
            level="warning" if budget.exhausted_reason or state.get("cancel_requested") else "info",
            message=(
                f"审查调度完成：完成 {budget.completed_units}/{len(state.get('review_units', []))} 个单元，"
                f"完成 {completed_assignments}/{planned_assignments} 个批次，"
                f"主要审查调用 {budget.primary_calls} 次，上下文读取请求 "
                f"{budget.context_read_requests} 次"
            ),
    )
    coverage.update(tool_stats)
    coverage["failed_batches"] = pending_assignments
    if state.get("cancel_requested") or budget.exhausted_reason:
        coverage["coverage_status"] = "incomplete"
    # 兼容旧 Reviewer 只写入 truncation_events 的情况；新路径中
    # truncation_events 仅包含会影响结论的关键截断。
    if not critical_truncation_events and legacy_truncated_inputs:
        critical_truncation_events.update(truncation_events)
    truncation_events = critical_truncation_events
    truncated_inputs = len(truncation_events)
    coverage["truncation_events"] = sorted(truncation_events)
    coverage["critical_truncation_events"] = sorted(truncation_events)
    coverage["critical_truncated_inputs"] = truncated_inputs
    coverage["context_limit_events"] = sorted(context_limit_events)
    coverage["context_limited_inputs"] = len(context_limit_events)
    coverage["truncated_inputs"] = truncated_inputs
    coverage.update(_aggregate_llm_usage(reviewer_outputs))
    diagnostics = _aggregate_review_diagnostics(reviewer_outputs)
    existing_failure_events = coverage.get("context_request_failure_events", [])
    failure_events: list[dict] = []
    failure_event_keys: set[str] = set()
    for event in [
        *existing_failure_events,
        *diagnostics["context_request_failure_events"],
    ]:
        event_key = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
        if event_key not in failure_event_keys:
            failure_events.append(event)
            failure_event_keys.add(event_key)
    diagnostics["context_request_failure_events"] = failure_events
    diagnostics["context_request_failures"] = len(failure_events)
    coverage.update(diagnostics)
    state["coverage"] = coverage

    rejection_reasons: dict[str, int] = {}
    accepted_findings = filter_findings(
        all_findings,
        state.get("changed_files", []),
        state.get("raw_diff", ""),
        repo_root=state.get("repo_id") if state.get("tool_context") else None,
        approved_context_refs=state.get("approved_context_refs", []),
        rejection_reasons=rejection_reasons,
        require_changed_line=True,
    )
    metrics = compute_quality_metrics(
        all_findings,
        accepted_findings,
        reviewer_outputs,
        coverage,
        rejection_reasons=rejection_reasons,
    )
    metrics.update(
        {
            "database_id": state.get("database_id"),
            "database_status": state.get("database_status"),
            "extraction_status": state.get("extraction_status"),
            "extraction_planned_files": state.get("code_database_info", {}).get("planned_files", 0),
            "extracted_files": state.get("code_database_info", {}).get("extracted_files", 0),
            "extraction_errors": state.get("extraction_errors", []),
            "query_results": len(state.get("analysis_results", [])),
            "context_errors": state.get("context_errors", {}),
            "cancel_requested": bool(state.get("cancel_requested")),
            "reviewed_units": len({
                key.split(":context-", 1)[0]
                for key in state.get("completed_unit_ids", [])
            }),
            "context_covered_hunks": coverage.get("covered_hunks", 0),
            "planned_reviewer_assignments": planned_assignments,
            "reviewed_reviewer_assignments": budget.completed_assignments,
            "pending_reviewer_assignments": pending_assignments,
            **state.get("review_budget", {}),
        }
    )
    state["quality_metrics"] = metrics

    checks = list(state.get("checks", []))
    check_updates: list[dict] = []
    for error in workflow_errors:
        error_source = error.get("reviewer") or error.get("source") or "workflow"
        check_updates.append(
            {
                "name": f"reviewer_{error_source}",
                "status": "error",
                "message": error["message"],
            }
        )
    check_updates.extend(build_quality_checks(metrics))
    state["checks"] = merge_checks(checks, check_updates)
    state["findings"] = accepted_findings
    return state
