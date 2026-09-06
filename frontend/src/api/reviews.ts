import api from "./client";
import type { ReviewTask, ReviewReportResponse, PRItem, CommitItem, ReviewLog } from "../types";

export const reviewApi = {
  submit: (repoId: string, data: { review_type?: string; source_type?: string; pr_number?: number; commit_hash?: string; branch?: string; workspace_path?: string; workspace_target?: string }) =>
    api.post<ReviewTask>(`/repos/${repoId}/reviews`, data),
  list: (repoId: string, includeArchived = false) => api.get<ReviewTask[]>(`/repos/${repoId}/reviews`, { params: { include_archived: includeArchived } }),
  status: (taskId: string) => api.get<ReviewTask>(`/reviews/${taskId}`),
  report: (taskId: string) => api.get<ReviewReportResponse>(`/reviews/${taskId}/report`),
  listPRs: (repoId: string) => api.get<PRItem[]>(`/repos/${repoId}/prs`),
  listCommits: (repoId: string, branch?: string, limit = 20) => api.get<CommitItem[]>(`/repos/${repoId}/commits`, { params: { limit, branch } }),
  logs: (taskId: string) => api.get<ReviewLog[]>(`/reviews/${taskId}/logs`),
  cancel: (taskId: string) => api.post<ReviewTask>(`/reviews/${taskId}/cancel`),
  archive: (taskId: string) => api.post<ReviewTask>(`/reviews/${taskId}/archive`),
  restore: (taskId: string) => api.post<ReviewTask>(`/reviews/${taskId}/restore`),
  remove: (taskId: string) => api.delete(`/reviews/${taskId}`),
};
