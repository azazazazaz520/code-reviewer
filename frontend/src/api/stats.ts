import api from "./client";
import type { OverviewStats, HeatmapData } from "../types";

export const statsApi = {
  overview: () => api.get<OverviewStats>("/stats/overview"),
  heatmap: () => api.get<HeatmapData>("/stats/heatmap"),
};
