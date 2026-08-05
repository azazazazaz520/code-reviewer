import api from "./client";
import type { BranchItem, Repo } from "../types";

export const repoApi = {
  list: () => api.get<Repo[]>("/repos"),
  create: (data: { name: string; git_url: string }) =>
    api.post<Repo>("/repos", data),
  get: (id: string) => api.get<Repo>(`/repos/${id}`),
  update: (id: string, data: { name: string; git_url: string }) =>
    api.put<Repo>(`/repos/${id}`, data),
  branches: (id: string) => api.get<BranchItem[]>(`/repos/${id}/branches`),
  remove: (id: string) => api.delete(`/repos/${id}`),
};
