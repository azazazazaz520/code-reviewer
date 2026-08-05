from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ─── 仓库 ──────────────────────────────────────────

class RepoCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    git_url: str = Field(..., min_length=1, max_length=500)
    local_path: str | None = Field(default=None, max_length=500)


class RepoResponse(BaseModel):
    id: str
    name: str
    git_url: str
    local_path: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── 审查任务 ────────────────────────────────────────

class ReviewType(str, Enum):
    PR = "pr"
    LOCAL = "local"


class ReviewCreate(BaseModel):
    review_type: ReviewType
    pr_number: int | None = None
    commit_hash: str | None = None
    branch: str | None = Field(default=None, max_length=200)
    base_branch: str | None = None


class ReviewTaskResponse(BaseModel):
    id: str
    repo_id: str
    repo_name: str | None = None  # 仓库名称，由 API 层填充
    review_type: str
    pr_number: int | None = None
    commit_hash: str | None = None
    branch: str | None = None
    base_branch: str | None = None
    status: str
    risk_level: str | None = None  # 从 review_reports JOIN 获取
    error_message: str | None = None
    reflection_rounds: int
    created_at: datetime
    completed_at: datetime | None = None
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


# ─── 审查发现 ────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingSchema(BaseModel):
    severity: Severity
    file: str
    line: int
    title: str
    reason: str
    suggestion: str


class ReviewStats(BaseModel):
    total_findings: int
    by_severity: dict[str, int]
    impacted_files: int
    test_gaps: int


class ReviewCheck(BaseModel):
    name: str
    status: str
    message: str


class ReviewQualityMetrics(BaseModel):
    candidate_findings: int = 0
    accepted_findings: int = 0
    filtered_findings: int = 0
    located_findings: int = 0
    static_evidence_findings: int = 0
    reviewer_context_findings: int = 0


class ReviewerOutputAttempt(BaseModel):
    stage: str
    output: str
    truncated: bool = False


class ReviewerOutputTrace(BaseModel):
    attempts: list[ReviewerOutputAttempt] = Field(default_factory=list)
    candidate_findings: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None


class ReviewReportResponse(BaseModel):
    review_id: str
    status: str
    report: "ReportContent | None" = None


class ReviewChanges(BaseModel):
    review_type: str = ""
    pr_number: int | None = None
    commit_hash: str | None = None
    branch: str | None = None
    base_branch: str | None = None
    base_revision: str | None = None
    head_revision: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    diff: str = ""


class ReportContent(BaseModel):
    summary: str
    risk_level: RiskLevel
    findings: list[FindingSchema]
    stats: ReviewStats
    review_status: str = "complete"
    checks: list[ReviewCheck] = Field(default_factory=list)
    quality: ReviewQualityMetrics = Field(default_factory=ReviewQualityMetrics)
    reviewer_outputs: dict[str, ReviewerOutputTrace] = Field(default_factory=dict)
    changes: ReviewChanges = Field(default_factory=ReviewChanges)


# ─── 统计 ──────────────────────────────────────────

class OverviewStats(BaseModel):
    total_reviews: int
    reviews_this_month: int
    active_repos: int
    risk_distribution: dict[str, int]
    recent_reviews: list[ReviewTaskResponse]


class HotspotItem(BaseModel):
    file: str
    count: int


class RepoStats(BaseModel):
    total_reviews: int
    risk_distribution: dict[str, int]
    hotspots: list[HotspotItem]
    recent_reviews: list[ReviewTaskResponse]


# ─── 热力图 ──────────────────────────────────────────

class HeatmapCell(BaseModel):
    month: str  # "2026-01"
    review_count: int
    worst_risk: str | None = None  # null 表示该月无已完成审查


class HeatmapRepoRow(BaseModel):
    repo_id: str
    repo_name: str
    cells: list[HeatmapCell]


class HeatmapResponse(BaseModel):
    months: list[str]
    repos: list[HeatmapRepoRow]


# ─── PR / Commit 列表 ─────────────────────────────────

class PRItem(BaseModel):
    number: int
    title: str
    author: str
    branch: str
    created_at: str  # ISO 8601 字符串


class CommitItem(BaseModel):
    hash: str  # 完整 hash
    short_hash: str  # 前 7 位
    message: str
    author: str
    date: str  # ISO 8601 字符串


class BranchItem(BaseModel):
    name: str


# ─── 审查日志 ──────────────────────────────────────────

class ReviewLogResponse(BaseModel):
    id: str
    task_id: str
    step: str
    level: str
    message: str
    tool_name: str | None = None
    tool_args: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
