"""ReviewState — LangGraph Workflow 的全局状态类型。"""

from typing import TypedDict


class ReviewState(TypedDict, total=False):
    task_id: str

    # PR 元信息
    repo_id: str
    review_type: str  # "pr" | "local"
    source_type: str | None
    pr_number: int | None
    commit_hash: str | None
    branch: str | None
    base_branch: str | None
    git_url: str  # GitHub/Gitee 仓库 URL（PR 模式用）

    # Diff 和变更文件
    raw_diff: str
    changed_files: list[str]
    snapshot_revision: str
    snapshot_base_revision: str
    workspace_fingerprint: str | None
    workspace_stats: dict[str, int] | None
    review_scope: dict
    database_id: str
    database_status: str
    extraction_status: str
    extraction_errors: list[dict]
    database_stats: dict
    code_database_info: dict
    code_database: object
    tool_context: object
    approved_context_refs: list[dict]
    analysis_results: list[dict]
    coverage: dict
    context_candidates: list[str]
    context_round: int
    context_initialized: bool
    context_errors: dict[str, str]
    context_progress: dict[str, dict]
    candidate_findings: list[dict]
    change_scopes: dict[str, str]

    # 确定性校验与审查质量
    validator_findings: list[dict]
    checks: list[dict]
    workflow_errors: list[dict]
    quality_metrics: dict
    reviewer_outputs: dict[str, dict]
    reviewed_batch_keys: dict[str, list[str]]
    review_units: list[dict]
    review_batches: dict[str, list[dict]]
    reviewed_unit_keys: dict[str, list[str]]
    completed_batch_keys: dict[str, list[str]]
    completed_unit_ids: list[str]
    pending_unit_ids: list[str]
    review_budget: dict
    tool_cache: object
    cancel_requested: bool

    # 审查计划
    review_plan: list[str]  # ["security_reviewer", "style_reviewer", ...]

    # 文件上下文缓存（file_path → content）
    file_context_cache: dict[str, str]

    # 审查发现
    findings: list[dict]

    # 最终报告
    summary: str
    risk_level: str  # "low" / "medium" / "high" / "critical"
    review_status: str  # "complete" / "degraded"
    report: dict  # 最终输出

    # CRG 集成（可选）
    crg_enabled: bool
    impact_radius: dict | None

    # 日志回调（审查进度实时推送）
    _log_hook: object
    _cancel_check: object
    _review_budget_object: object
