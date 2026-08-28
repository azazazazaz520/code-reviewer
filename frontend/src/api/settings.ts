import api from "./client";
import type {
  EffectiveSettingsSnapshot,
  LLMSettingsPatch,
  SettingsPatch,
  SettingsUpdateResponse,
} from "../types/settings";

export const settingsApi = {
  get: () => api.get<EffectiveSettingsSnapshot>("/settings"),
  update: (expectedVersion: number, settings: SettingsPatch) =>
    api.patch<SettingsUpdateResponse>("/settings", {
      expected_version: expectedVersion,
      settings,
    }),
  testLlm: (draft: LLMSettingsPatch) =>
    api.post<{ ok: boolean; message: string }>("/settings/test/llm", draft, { timeout: 15000 }),
};
