import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReviewHeader from "./ReviewHeader";
import type { ReviewTask } from "../types";

const task: ReviewTask = {
  id: "task-1",
  repo_id: "repo-1",
  repo_name: "review-repo",
  review_type: "local",
  source_type: "remote_commit",
  pr_number: null,
  commit_hash: "abcdef1234567890",
  branch: "feature/review",
  base_branch: "main",
  head_revision: "abcdef1234567890",
  base_revision: "1234567890abcdef",
  status: "running",
  risk_level: null,
  error_message: null,
  reflection_rounds: 0,
  created_at: "2026-08-12T00:00:00Z",
  completed_at: null,
  archived_at: null,
};

describe("ReviewHeader", () => {
  it("在运行状态保留页面身份和审查上下文", () => {
    render(<ReviewHeader task={task} report={null} />);

    expect(screen.getByRole("heading", { name: "代码审查" })).toBeInTheDocument();
    expect(screen.getByText("仓库：review-repo")).toBeInTheDocument();
    expect(screen.getByText("远程指定 Commit")).toBeInTheDocument();
    expect(screen.getByText("feature/review")).toBeInTheDocument();
    expect(screen.getAllByText("审查进行中")).toHaveLength(2);
  });
});
