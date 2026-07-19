from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ─── 仓库 ──────────────────────────────────────────

class RepoCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    git_url: str = Field(..., min_length=1, max_length=500)
    local_path: str = Field(..., min_length=1, max_length=500)
    default_branch: str = Field(default="main", max_length=100)


class RepoResponse(BaseModel):
    id: str
    name: str
    git_url: str
    local_path: str
    default_branch: str
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
    base_branch: str | None = None


class ReviewTaskResponse(BaseModel):
    id: str
    repo_id: str
    repo_name: str | None = None  # 仓库名称，由 API 层填充
    review_type: str
    pr_number: int | None = None
    commit_hash: str | None = None
    base_branch: str | None = None
    status: str
    error_message: str | None = None
    reflection_rounds: int
    created_at: datetime
    completed_at: datetime | None = None

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


class ReviewReportResponse(BaseModel):
    review_id: str
    status: str
    report: "ReportContent | None" = None


class ReportContent(BaseModel):
    summary: str
    risk_level: RiskLevel
    findings: list[FindingSchema]
    stats: ReviewStats


# ─── 统计 ──────────────────────────────────────────

class OverviewStats(BaseModel):
    total_reviews: int
    reviews_this_month: int
    avg_risk_level: str
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
