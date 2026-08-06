export interface Repo {
  id: string;
  name: string;
  git_url: string;
  local_path?: string;  // backend auto-fills, not shown/edited in UI
  default_branch?: string | null;
  last_synced_at?: string | null;
  sync_status?: "never" | "syncing" | "ready" | "failed" | string;
  sync_error?: string | null;
  created_at: string;
}

export interface ReviewTask {
  id: string;
  repo_id: string;
  repo_name?: string;
  review_type: "pr" | "local";
  source_type?: "pr" | "remote_latest" | "remote_commit" | "workspace" | string | null;
  pr_number: number | null;
  commit_hash: string | null;
  branch: string | null;
  base_branch: string | null;
  head_revision: string | null;
  base_revision: string | null;
  workspace_target?: string | null;
  workspace_fingerprint?: string | null;
  workspace_stats_json?: string | null;
  status: "pending" | "running" | "preparing" | "done" | "failed";
  risk_level?: string | null;
  error_message: string | null;
  reflection_rounds: number;
  created_at: string;
  completed_at: string | null;
  archived_at: string | null;
}

export interface Finding {
  severity: "critical" | "high" | "medium" | "low";
  file: string;
  line: number;
  title: string;
  reason: string;
  suggestion: string;
  evidence_type?: "reviewer" | "reviewer_context" | "static_check" | "tool_verified" | string;
}

export interface ReviewReport {
  summary: string;
  risk_level: "low" | "medium" | "high" | "critical";
  review_status?: "complete" | "degraded" | string;
  findings: Finding[];
  checks?: ReviewCheck[];
  quality?: ReviewQualityMetrics;
  reviewer_outputs?: Record<string, ReviewerOutputTrace>;
  changes: ReviewChanges;
  stats: {
    total_findings: number;
    by_severity: Record<string, number>;
    impacted_files: number;
    test_gaps: number;
  };
}

export interface ReviewChanges {
  review_type: "pr" | "local" | string;
  source_type?: "pr" | "remote_latest" | "remote_commit" | "workspace" | string | null;
  pr_number: number | null;
  commit_hash: string | null;
  branch: string | null;
  base_branch: string | null;
  base_revision: string | null;
  head_revision: string | null;
  workspace_fingerprint?: string | null;
  workspace_stats?: Record<string, number> | null;
  changed_files: string[];
  diff: string;
}

export interface ReviewCheck {
  name: string;
  status: "pass" | "fail" | "unverified" | "error" | string;
  message: string;
}

export interface ReviewerOutputAttempt {
  stage: string;
  output: string;
  truncated: boolean;
}

export interface ReviewerOutputTrace {
  attempts: ReviewerOutputAttempt[];
  candidate_findings: Finding[];
  error_message: string | null;
}

export interface ReviewQualityMetrics {
  candidate_findings: number;
  accepted_findings: number;
  filtered_findings: number;
  truncated_outputs?: number;
  located_findings: number;
  static_evidence_findings: number;
  reviewer_context_findings: number;
}

export interface ReviewReportResponse {
  review_id: string;
  status: string;
  report: ReviewReport | null;
}

export interface OverviewStats {
  total_reviews: number;
  reviews_this_month: number;
  active_repos: number;
  risk_distribution: Record<string, number>;
  recent_reviews: ReviewTask[];
}

// ─── 热力图 ──────────────────────────────────────

export interface HeatmapCell {
  month: string;
  review_count: number;
  worst_risk: string | null;
}

export interface HeatmapRepoRow {
  repo_id: string;
  repo_name: string;
  cells: HeatmapCell[];
}

export interface HeatmapData {
  months: string[];
  repos: HeatmapRepoRow[];
}

// ─── PR / Commit 列表 ─────────────────────────────

export interface PRItem {
  number: number;
  title: string;
  author: string;
  branch: string;
  created_at: string;
}

export interface CommitItem {
  hash: string;
  short_hash: string;
  message: string;
  author: string;
  date: string;
}

export interface BranchItem {
  name: string;
  head_revision?: string | null;
  previous_revision?: string | null;
  has_new_commits?: boolean;
}

export interface SyncResponse {
  status: string;
  checked_at: string;
  default_branch: string | null;
  branches: BranchItem[];
  error?: string | null;
}

export interface ReviewLog {
  id: string;
  task_id: string;
  step: string;
  level: string;
  message: string;
  tool_name?: string | null;
  tool_args?: string | null;
  created_at: string;
}
