import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PromptWorkbench from "./PromptWorkbench";

const promptApiMocks = vi.hoisted(() => ({
  optimize: vi.fn(),
  addTurn: vi.fn(),
  removeSession: vi.fn(),
}));

vi.mock("../api/prompts", () => ({ promptApi: promptApiMocks }));

const response = {
  result: {
    classification: { type: "bug", confidence: 0.9, reason: "存在状态异常" },
    problem_phenomenon: "操作后状态未保持",
    technical_essence: "状态更新链路不一致",
    solution: ["检查状态写入链路"],
    bug_view: "需要补充复现步骤",
    prd_view: "明确状态保持范围",
    team_message: "状态未稳定保持",
    term_mappings: [],
    assumptions: [],
    checks: [],
  },
  turn: 1,
  max_turns: 3,
  session_id: null,
  expires_at: null,
  metadata: {
    model: "test-model",
    prompt_id: "devprompt-pro",
    prompt_version: "1.0.0",
    schema_version: "1",
    elapsed_ms: 10,
    llm_attempts: 1,
    format_repaired: false,
    candidate_mapping_count: 0,
    turn: 1,
  },
  exports: {
    markdown: "# 服务端 Markdown",
    jira: "h2. 服务端 Jira",
    issue: "## 服务端 Issue",
  },
};

describe("PromptWorkbench", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    promptApiMocks.optimize.mockResolvedValue({ data: response });
    promptApiMocks.removeSession.mockResolvedValue({});
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it("使用 Prompt 工具箱名称并使用服务端导出结果", async () => {
    render(
      <MemoryRouter>
        <PromptWorkbench />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Prompt 工具箱" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("原始描述"), {
      target: { value: "点击后状态没有保持" },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成结构化结果" }));

    expect(await screen.findByText("操作后状态未保持")).toBeInTheDocument();
    expect(promptApiMocks.optimize).toHaveBeenCalledWith(expect.objectContaining({
      content: "点击后状态没有保持",
      mode: "instant",
    }));

    fireEvent.click(screen.getByRole("button", { name: "复制 Markdown" }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("# 服务端 Markdown");
    });
  });
});
