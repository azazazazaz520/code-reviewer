"""ReviewState — LangGraph Workflow 的全局状态类型。"""

from typing import TypedDict


class ReviewState(TypedDict, total=False):
    # PR 元信息
    repo_id: str
    review_type: str  # "pr" | "local"
    pr_number: int | None
    commit_hash: str | None
    base_branch: str | None
    git_url: str  # GitHub 仓库 URL（PR 模式用）

    # Diff 和变更文件
    raw_diff: str
    changed_files: list[str]
    snapshot_revision: str
    snapshot_base_revision: str
    context_candidates: list[str]
    context_round: int
    context_initialized: bool

    # 审查计划
    review_plan: list[str]  # ["security_reviewer", "style_reviewer", ...]

    # 文件上下文缓存（file_path → content）
    file_context_cache: dict[str, str]

    # 审查发现
    findings: list[dict]

    # Reflection 循环
    reflection_round: int
    need_more_context: bool

    # 最终报告
    summary: str
    risk_level: str  # "low" / "medium" / "high" / "critical"
    report: dict  # 最终输出

    # CRG 集成（可选）
    crg_enabled: bool
    impact_radius: dict | None

    # 日志回调（审查进度实时推送）
    _log_hook: object
