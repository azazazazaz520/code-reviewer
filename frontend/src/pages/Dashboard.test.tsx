import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HeatmapData, OverviewStats, ReviewTask } from "../types";
import Dashboard from "./Dashboard";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  heatmap: vi.fn(),
  archive: vi.fn(),
}));

vi.mock("../api/stats", () => ({
  statsApi: {
    overview: mocks.overview,
    heatmap: mocks.heatmap,
  },
}));

vi.mock("../api/reviews", () => ({
  reviewApi: {
    archive: mocks.archive,
  },
}));

vi.mock("../components/ReviewHeatmap", () => ({
  default: () => <div data-testid="review-heatmap" />,
}));

vi.mock("../components/SubmitReviewModal", () => ({
  default: () => null,
}));

const review: ReviewTask = {
  id: "review-1",
  repo_id: "repo-1",
  repo_name: "demo-repo",
  review_type: "local",
  source_type: "remote_commit",
  pr_number: null,
  commit_hash: "abcdef1234567",
  branch: "main",
  base_branch: null,
  head_revision: "abcdef1234567",
  base_revision: null,
  workspace_target: null,
  workspace_fingerprint: null,
  workspace_stats_json: null,
  status: "done",
  risk_level: "low",
  error_message: null,
  reflection_rounds: 1,
  created_at: "2026-08-29T00:00:00Z",
  completed_at: "2026-08-29T00:01:00Z",
  archived_at: null,
};

const stats: OverviewStats = {
  total_reviews: 1,
  reviews_this_month: 1,
  active_repos: 1,
  risk_distribution: { low: 1, medium: 0, high: 0, critical: 0 },
  recent_reviews: [review],
};

const heatmap: HeatmapData = { months: [], repos: [] };

describe("Dashboard 归档交互", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.overview.mockResolvedValue({ data: stats });
    mocks.heatmap.mockResolvedValue({ data: heatmap });
    mocks.archive.mockResolvedValue({ data: { ...review, archived_at: "2026-08-29T00:02:00Z" } });
  });

  it("归档后只移除列表记录，后台刷新不替换整页，并显示已归档浮窗", async () => {
    let resolveRefresh: ((value: { data: OverviewStats }) => void) | undefined;
    const refreshPromise = new Promise<{ data: OverviewStats }>((resolve) => {
      resolveRefresh = resolve;
    });
    mocks.overview
      .mockResolvedValueOnce({ data: stats })
      .mockReturnValueOnce(refreshPromise);

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );

    await screen.findByText("demo-repo");
    fireEvent.click(screen.getByRole("button", { name: "归档" }));

    await waitFor(() => expect(mocks.archive).toHaveBeenCalledWith("review-1"));
    await waitFor(() => expect(mocks.overview).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("demo-repo")).not.toBeInTheDocument();
    expect(document.querySelector('[data-slot="skeleton"]')).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("已归档");

    resolveRefresh?.({ data: { ...stats, recent_reviews: [] } });
  });

  it("归档失败时保留记录并显示错误提示", async () => {
    mocks.archive.mockRejectedValueOnce(new Error("请求失败"));

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );

    await screen.findByText("demo-repo");
    fireEvent.click(screen.getByRole("button", { name: "归档" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("归档失败");
    expect(screen.getByText("demo-repo")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
