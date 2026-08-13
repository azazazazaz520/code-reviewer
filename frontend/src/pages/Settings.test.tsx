import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "../components/theme-provider";
import type { EffectiveSettingsSnapshot } from "../types/settings";
import Settings from "./Settings";

const snapshot: EffectiveSettingsSnapshot = {
  schema_version: 1,
  config_version: 0,
  sources: {
    "llm.model": "default",
    "llm.base_url": "env",
    "llm.temperature": "default",
    "llm.max_tokens": "default",
    "review.max_reflection_rounds": "default",
    "review.context_files_per_round": "default",
    "review.crg_enabled": "default",
    "prompt.timeout_seconds": "default",
    "prompt.min_input_chars": "default",
    "prompt.max_input_chars": "default",
    "prompt.max_output_tokens": "default",
    "prompt.session_ttl_seconds": "default",
    "prompt.session_max_count": "default",
    "prompt.session_max_context_chars": "default",
    "storage.repos_dir": "env",
  },
  settings: {
    llm: {
      provider: "deepseek-openai-compatible",
      model: "deepseek-chat",
      base_url: "https://api.deepseek.com/v1",
      temperature: 0.1,
      max_tokens: 4096,
    },
    review: { max_reflection_rounds: 3, context_files_per_round: 20, crg_enabled: true },
    prompt: {
      timeout_seconds: 60,
      min_input_chars: 1,
      max_input_chars: 12000,
      max_output_tokens: 3000,
      session_ttl_seconds: 1800,
      session_max_count: 100,
      session_max_context_chars: 24000,
    },
    storage: { repos_dir: "./data/repos" },
  },
  secret_status: {
    llm_api_key: "not_configured",
    github_token: "configured",
    gitee_token: "not_configured",
  },
};

vi.mock("../hooks/use-settings", () => ({
  useSettings: () => ({
    snapshot,
    runtime: null,
    sidecarState: null,
    runtimeError: null,
    loading: false,
    error: null,
    reload: vi.fn(),
  }),
}));

describe("Settings", () => {
  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: (query: string) => ({
        matches: query.includes("prefers-color-scheme: dark") ? false : false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
  });

  it("支持分区切换并显示当前配置来源和敏感状态", () => {
    render(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>,
    );

    expect(screen.getByRole("heading", { name: "设置" })).toBeInTheDocument();
    expect(screen.getByText("跟随系统")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /模型服务/ }));
    expect(screen.getByText("deepseek-chat")).toBeInTheDocument();
    expect(screen.getByText("来源：环境配置")).toBeInTheDocument();
    expect(screen.getByText("模型服务 API Key")).toBeInTheDocument();
    expect(screen.getByText("未配置")).toBeInTheDocument();
  });

  it("主题立即生效并保持本地偏好，浏览器模式显示路径能力限制", () => {
    render(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByRole("radio", { name: /深色/ }));
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");

    fireEvent.change(screen.getByRole("combobox", { name: "设置分区" }), { target: { value: "storage" } });
    expect(screen.getByText("浏览器模式不具备打开本地路径的桌面能力。")).toBeInTheDocument();
  });
});
