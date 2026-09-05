import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReviewProgress from "./ReviewProgress";
import type { ReviewLog } from "../types";

const log = (
  id: string,
  message: string,
  step = "run_reviews",
  level = "info",
): ReviewLog => ({
  id,
  task_id: "task-1",
  step,
  level,
  message,
  tool_name: null,
  tool_args: null,
  created_at: "2026-08-12T00:00:00Z",
});

describe("ReviewProgress", () => {
  it("播报状态并在用户离开底部后提供新日志恢复入口", () => {
    const initialLogs = [log("1", "开始执行")];
    const { rerender } = render(<ReviewProgress logs={initialLogs} logPolling />);
    const logContainer = screen.getByRole("log");
    Object.defineProperty(logContainer, "scrollHeight", { configurable: true, value: 400 });
    Object.defineProperty(logContainer, "clientHeight", { configurable: true, value: 100 });
    Object.defineProperty(logContainer, "scrollTop", { configurable: true, writable: true, value: 0 });

    expect(screen.getByRole("status")).toHaveTextContent("审查进行中");
    fireEvent.scroll(logContainer);
    rerender(<ReviewProgress logs={[...initialLogs, log("2", "继续执行")]} logPolling />);

    expect(screen.getByRole("button", { name: "有新日志，回到底部" })).toBeInTheDocument();
  });

  it("按工作流阶段标记完成、当前和待执行状态", () => {
    render(
      <ReviewProgress
        logs={[
          log("1", "来源已准备", "prepare_source"),
          log("2", "变更已获取", "load_pr"),
          log("3", "正在收集上下文", "collect_context"),
          log("4", "正在规划策略", "planning"),
        ]}
        logPolling
      />,
    );

    expect(screen.getByRole("progressbar", { name: "审查阶段进度" })).toHaveAttribute("aria-valuenow", "3");
    expect(screen.getByText("准备审查来源").closest("li")).toHaveAttribute("data-status", "done");
    expect(screen.getByText("规划策略").closest("li")).toHaveAttribute("data-status", "active");
    expect(screen.getByText("执行审查").closest("li")).toHaveAttribute("data-status", "pending");
  });

  it("在完成和失败时分别标记终态", () => {
    const { rerender } = render(
      <ReviewProgress
        logs={[log("1", "审查完成", "generate_report")]}
        logPolling={false}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("审查完成");
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getByText("生成报告").closest("li")).toHaveAttribute("data-status", "done");

    rerender(
      <ReviewProgress
        logs={[
          log("1", "来源已准备", "prepare_source"),
          log("2", "变更已获取", "load_pr"),
          log("3", "审查执行失败", "run_reviews", "error"),
        ]}
        logPolling={false}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("审查失败");
    expect(screen.getByText("执行审查").closest("li")).toHaveAttribute("data-status", "failed");
    expect(screen.getByText("反思").closest("li")).toHaveAttribute("data-status", "pending");
  });
});
