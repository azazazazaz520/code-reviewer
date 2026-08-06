import api from "./client";
import type { BranchItem, Repo, SyncResponse } from "../types";

export const repoApi = {
  list: () => api.get<Repo[]>("/repos"),
  create: (data: { name: string; git_url: string }) =>
    api.post<Repo>("/repos", data),
  createWorkspace: (data: { path: string; name?: string }) =>
    api.post<Repo>("/repos/workspace", data),
  updateWorkspace: (id: string, data: { path: string; name?: string }) =>
    api.put<Repo>(`/repos/${id}/workspace`, data),
  get: (id: string) => api.get<Repo>(`/repos/${id}`),
  update: (id: string, data: { name: string; git_url: string }) =>
    api.put<Repo>(`/repos/${id}`, data),
  branches: (id: string) => api.get<BranchItem[]>(`/repos/${id}/branches`),
  sync: (id: string) => api.post<SyncResponse>(`/repos/${id}/sync`),
  remove: (id: string) => api.delete(`/repos/${id}`),
};
