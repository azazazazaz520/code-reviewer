import api from "./client";
import type { ReviewTask, ReviewReportResponse, PRItem, CommitItem } from "../types";

export const reviewApi = {
  submit: (repoId: string, data: { review_type: string; pr_number?: number; commit_hash?: string }) =>
    api.post<ReviewTask>(`/repos/${repoId}/reviews`, data),
  list: (repoId: string) => api.get<ReviewTask[]>(`/repos/${repoId}/reviews`),
  status: (taskId: string) => api.get<ReviewTask>(`/reviews/${taskId}`),
  report: (taskId: string) => api.get<ReviewReportResponse>(`/reviews/${taskId}/report`),
  listPRs: (repoId: string) => api.get<PRItem[]>(`/repos/${repoId}/prs`),
  listCommits: (repoId: string, limit = 20) => api.get<CommitItem[]>(`/repos/${repoId}/commits`, { params: { limit } }),
};
