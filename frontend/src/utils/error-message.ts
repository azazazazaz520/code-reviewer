import axios from "axios";

export interface UserErrorInfo {
  message: string;
  diagnostic: string;
  status?: number;
  retryable: boolean;
  action: "retry" | "configure" | "check-service";
}

type ErrorPayload = {
  response?: {
    status?: number;
    data?: { detail?: unknown; message?: unknown; error?: unknown };
  };
  code?: string;
  message?: string;
};

function extractDetail(error: ErrorPayload): string {
  const detail = error.response?.data?.detail ?? error.response?.data?.message ?? error.response?.data?.error;
  if (typeof detail === "string") return detail.trim();
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message.trim();
  }
  return "";
}

function isTechnicalMessage(message: string): boolean {
  return /request failed|network error|timeout|timed out|status code|err_|econn|enotfound|fetch failed/i.test(message);
}

function mapKnownServiceMessage(message: string): string | null {
  const lowered = message.toLowerCase();
  if (lowered.includes("insufficient balance") || (lowered.includes("402") && lowered.includes("balance"))) {
    return "模型服务余额不足，请补充余额或更换模型服务后重试。";
  }
  if (lowered.includes("invalid api key") || lowered.includes("authentication") || lowered.includes("401")) {
    return "模型服务认证失败，请检查相关配置后重试。";
  }
  if (lowered.includes("rate limit") || lowered.includes("too many requests") || lowered.includes("429")) {
    return "请求过于频繁，请稍后重试。";
  }
  if (lowered.includes("502") || lowered.includes("503") || lowered.includes("bad gateway") || lowered.includes("service unavailable")) {
    return "审查服务暂时不可用，请确认服务已启动后重试。";
  }
  if (lowered.includes("timeout") || lowered.includes("timed out")) {
    return "请求处理时间较长，请稍后重试。";
  }
  if (lowered.includes("network error") || lowered.includes("econnrefused") || lowered.includes("fetch failed")) {
    return "无法连接到审查服务，请检查服务状态或网络。";
  }
  return null;
}

export function toUserError(error: unknown, fallback: string): UserErrorInfo {
  if (error && typeof error === "object" && "message" in error && "diagnostic" in error) {
    return error as UserErrorInfo;
  }

  const payload = (error && typeof error === "object" ? error : {}) as ErrorPayload;
  const status = axios.isAxiosError(error) ? error.response?.status : payload.response?.status;
  const code = payload.code || (axios.isAxiosError(error) ? error.code : undefined);
  const detail = extractDetail(payload);
  const rawMessage = detail || payload.message || (typeof error === "string" ? error : "");
  const timeout = code === "ECONNABORTED" || code === "ETIMEDOUT" || /timeout|timed out/i.test(rawMessage);
  const noResponse = axios.isAxiosError(error) && !error.response;

  let message = fallback;
  let action: UserErrorInfo["action"] = "retry";
  if (status === 401) {
    message = "服务认证失败，请检查相关配置后重试。";
    action = "configure";
  } else if (status === 402) {
    message = "模型服务余额不足，请补充余额或更换服务后重试。";
    action = "configure";
  } else if (status === 429) {
    message = "请求过于频繁，请稍后重试。";
  } else if (status === 502 || status === 503) {
    message = "审查服务暂时不可用，请确认服务已启动后重试。";
    action = "check-service";
  } else if (timeout) {
    message = "请求处理时间较长，请稍后重试。";
  } else if (noResponse) {
    message = "无法连接到审查服务，请检查服务状态或网络。";
    action = "check-service";
  } else if (rawMessage && !isTechnicalMessage(rawMessage)) {
    message = mapKnownServiceMessage(rawMessage) || rawMessage;
  } else if (rawMessage) {
    message = mapKnownServiceMessage(rawMessage) || fallback;
  }

  const diagnostic = [
    status ? `HTTP ${status}` : "",
    code ? `code=${code}` : "",
    rawMessage && rawMessage !== message ? rawMessage : "",
  ].filter(Boolean).join(" · ");

  return { message, diagnostic, status, retryable: true, action };
}

export function formatErrorMessage(message: string | null | undefined): string {
  const raw = (message || "").trim();
  return mapKnownServiceMessage(raw) || raw || "模型服务调用失败，请稍后重试。";
}

const reviewerLabels: Record<string, string> = {
  style_reviewer: "代码风格审查",
  security_reviewer: "安全审查",
  performance_reviewer: "性能审查",
};

export function formatReviewerName(name: string): string {
  return reviewerLabels[name] || name;
}
