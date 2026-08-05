import api from "./client";
import type {
  PromptOptimizeRequest,
  PromptOptimizeResponse,
  PromptSessionResponse,
} from "../types/prompt";

export const promptApi = {
  optimize(request: PromptOptimizeRequest) {
    return api.post<PromptOptimizeResponse>("/prompts/optimize", request);
  },

  addTurn(sessionId: string, feedback: string) {
    return api.post<PromptOptimizeResponse>(
      `/prompts/sessions/${encodeURIComponent(sessionId)}/turns`,
      { feedback },
    );
  },

  getSession(sessionId: string) {
    return api.get<PromptSessionResponse>(
      `/prompts/sessions/${encodeURIComponent(sessionId)}`,
    );
  },

  removeSession(sessionId: string) {
    return api.delete(`/prompts/sessions/${encodeURIComponent(sessionId)}`);
  },
};
