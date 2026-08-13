import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReviewProgress from "./ReviewProgress";
import type { ReviewLog } from "../types";

const log = (id: string, message: string): ReviewLog => ({
  id,
  task_id: "task-1",
  step: "run_reviews",
  level: "info",
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
});
