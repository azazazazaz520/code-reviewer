import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RiskDistributionChart from "./RiskDistributionChart";

describe("RiskDistributionChart", () => {
  it("以环形图和明细展示各严重度数量与占比", () => {
    render(
      <RiskDistributionChart
        bySeverity={{ critical: 0, high: 0, medium: 2, low: 1 }}
        totalFindings={3}
      />,
    );

    expect(screen.getByRole("heading", { name: "风险分布" })).toBeInTheDocument();
    expect(screen.getByText("共 3 项风险")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "风险分布：严重 0 项，高危 0 项，中危 2 项，低危 1 项" })).toBeInTheDocument();
    expect(screen.getByText("风险主要集中在中危级别")).toBeInTheDocument();
    expect(screen.getByText("中危问题占全部发现的 67%。")).toBeInTheDocument();
    expect(screen.getByLabelText("风险等级明细")).toHaveTextContent("严重0(0%)高危0(0%)中危2(67%)低危1(33%)");
    expect(screen.getByTestId("risk-distribution-center")).toHaveClass("absolute", "inset-0");
  });

  it("在没有风险时展示空状态而不是伪造分布", () => {
    render(
      <RiskDistributionChart
        bySeverity={{ critical: 0, high: 0, medium: 0, low: 0 }}
        totalFindings={0}
      />,
    );

    expect(screen.getByText("暂无风险发现")).toBeInTheDocument();
    expect(screen.getByText("本次审查未发现需要展示的风险问题。")).toBeInTheDocument();
    expect(screen.getByText("共 0 项风险")).toBeInTheDocument();
  });
});
