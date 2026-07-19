import api from "./client";
import type { Repo } from "../types";

export const repoApi = {
  list: () => api.get<Repo[]>("/repos"),
  create: (data: { name: string; git_url: string; local_path: string; default_branch: string }) =>
    api.post<Repo>("/repos", data),
  get: (id: string) => api.get<Repo>(`/repos/${id}`),
  remove: (id: string) => api.delete(`/repos/${id}`),
};
