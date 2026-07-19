export interface Repo {
  id: string;
  name: string;
  git_url: string;
  local_path: string;
  default_branch: string;
  created_at: string;
}

export interface ReviewTask {
  id: string;
  repo_id: string;
  repo_name?: string;
  review_type: "pr" | "local";
  pr_number: number | null;
  commit_hash: string | null;
  base_branch: string | null;
  status: "pending" | "running" | "done" | "failed";
  error_message: string | null;
  reflection_rounds: number;
  created_at: string;
  completed_at: string | null;
}

export interface Finding {
  severity: "critical" | "high" | "medium" | "low";
  file: string;
  line: number;
  title: string;
  reason: string;
  suggestion: string;
}

export interface ReviewReport {
  summary: string;
  risk_level: "low" | "medium" | "high" | "critical";
  findings: Finding[];
  stats: {
    total_findings: number;
    by_severity: Record<string, number>;
    impacted_files: number;
    test_gaps: number;
  };
}

export interface ReviewReportResponse {
  review_id: string;
  status: string;
  report: ReviewReport | null;
}

export interface OverviewStats {
  total_reviews: number;
  reviews_this_month: number;
  avg_risk_level: string;
  active_repos: number;
  risk_distribution: Record<string, number>;
  recent_reviews: ReviewTask[];
}
