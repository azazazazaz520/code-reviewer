import api from "./client";
import type { OverviewStats } from "../types";

export const statsApi = {
  overview: () => api.get<OverviewStats>("/stats/overview"),
};
