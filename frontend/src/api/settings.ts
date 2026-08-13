import api from "./client";
import type { EffectiveSettingsSnapshot } from "../types/settings";

export const settingsApi = {
  get: () => api.get<EffectiveSettingsSnapshot>("/settings"),
};
