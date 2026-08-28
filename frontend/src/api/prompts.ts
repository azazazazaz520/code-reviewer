import api from "./client";
import type {
  PromptOptimizeRequest,
  PromptOptimizeResponse,
  PromptSessionResponse,
} from "../types/prompt";

// 提示词生成的 60 秒是一次请求总预算，客户端额外保留网络传输缓冲。
export const PROMPT_REQUEST_TIMEOUT_MS = 70_000;

export const promptApi = {
  optimize(request: PromptOptimizeRequest) {
    return api.post<PromptOptimizeResponse>("/prompts/optimize", request, {
      timeout: PROMPT_REQUEST_TIMEOUT_MS,
    });
  },

  addTurn(sessionId: string, feedback: string, expectedTurn: number, idempotencyKey: string) {
    return api.post<PromptOptimizeResponse>(
      `/prompts/sessions/${encodeURIComponent(sessionId)}/turns`,
      { feedback, expected_turn: expectedTurn, idempotency_key: idempotencyKey },
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
