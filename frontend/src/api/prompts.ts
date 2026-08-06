import api from "./client";
import type {
  PromptOptimizeRequest,
  PromptOptimizeResponse,
  PromptSessionResponse,
} from "../types/prompt";

// 提示词生成包含同步模型调用，客户端超时必须覆盖后端允许的 60 秒模型超时。
export const PROMPT_REQUEST_TIMEOUT_MS = 70_000;

export const promptApi = {
  optimize(request: PromptOptimizeRequest) {
    return api.post<PromptOptimizeResponse>("/prompts/optimize", request, {
      timeout: PROMPT_REQUEST_TIMEOUT_MS,
    });
  },

  addTurn(sessionId: string, feedback: string) {
    return api.post<PromptOptimizeResponse>(
      `/prompts/sessions/${encodeURIComponent(sessionId)}/turns`,
      { feedback },
      { timeout: PROMPT_REQUEST_TIMEOUT_MS },
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
