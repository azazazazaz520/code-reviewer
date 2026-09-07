import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "../components/theme-provider";
import type { EffectiveSettingsSnapshot } from "../types/settings";
import Settings from "./Settings";

const snapshot: EffectiveSettingsSnapshot = {
  schema_version: 2,
  config_version: 0,
  sources: {
    "llm.model": "default",
    "llm.base_url": "env",
    "llm.temperature": "default",
    "llm.max_tokens": "default",
    "llm.review_max_tokens": "default",
    "llm.supplement_max_tokens": "default",
    "llm.json_repair_max_tokens": "default",
    "review.crg_enabled": "default",
    "review.review_batch_max_chars": "default",
    "review.review_context_max_files": "default",
    "review.review_context_max_chars": "default",
    "review.supplement_context_max_chars": "default",
    "review.review_context_padding_lines": "default",
    "review.max_review_duration_seconds": "default",
    "review.review_parallelism": "default",
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
      model: "deepseek-v4-flash",
      base_url: "https://api.deepseek.com",
      temperature: 0.1,
      max_tokens: 4096,
      review_max_tokens: 4096,
      supplement_max_tokens: 2048,
      json_repair_max_tokens: 1024,
    },
    review: {
      crg_enabled: false,
      review_batch_max_chars: 12000,
      review_context_max_files: 10,
      review_context_max_chars: 32000,
      supplement_context_max_chars: 12000,
      review_context_padding_lines: 24,
      max_review_duration_seconds: 1200,
      review_parallelism: 3,
    },
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
    save: vi.fn(),
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
    expect(screen.getByDisplayValue("deepseek-v4-flash")).toBeInTheDocument();
    expect(screen.getByText("当前来源：环境配置")).toBeInTheDocument();
    expect(screen.getByText("模型服务 API Key")).toBeInTheDocument();
    expect(screen.getByText("未配置")).toBeInTheDocument();
  });

  it("切换设置分区不修改应用窗口标题", () => {
    document.title = "Code Reviewer";

    render(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /审查行为/ }));

    expect(document.title).toBe("Code Reviewer");
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

  it("保存设置后保持当前分区", async () => {
    render(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>,
    );

    fireEvent.change(screen.getByRole("combobox", { name: "设置分区" }), { target: { value: "review" } });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    expect(await screen.findByText("审查设置已保存")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "审查行为" })).toBeInTheDocument();
  });

  it("不向用户界面暴露研发阶段和实现限制文案", () => {
    render(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>,
    );

    for (const section of ["model", "git", "review", "prompt", "storage", "about"] as const) {
      fireEvent.change(screen.getByRole("combobox", { name: "设置分区" }), { target: { value: section } });
      expect(screen.queryByText(/P0|P1|只读模式|不提供|后续阶段|当前后端进程/)).not.toBeInTheDocument();
    }
  });
});
