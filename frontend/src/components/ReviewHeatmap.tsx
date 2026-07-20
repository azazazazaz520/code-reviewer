import { Table, Tooltip } from "antd";
import type { HeatmapData, HeatmapRepoRow, HeatmapCell } from "../types";
import type { ColumnsType } from "antd/es/table";

const riskColors: Record<string, string> = {
  low: "#52c41a",
  medium: "#faad14",
  high: "#fa8c16",
  critical: "#ff4d4f",
};

const emptyColor = "#f0f0f0";

const monthLabel = (month: string) => {
  const [, m] = month.split("-");
  return `${parseInt(m, 10)}月`;
};

interface HeatmapCellProps {
  cell: HeatmapCell;
  repoName: string;
  onClick: () => void;
}

function HeatmapCellView({ cell, repoName, onClick }: HeatmapCellProps) {
  const color = cell.worst_risk ? riskColors[cell.worst_risk] || emptyColor : emptyColor;
  const tooltip = cell.review_count > 0
    ? `${repoName} — ${cell.month}\n审查 ${cell.review_count} 次 · 最高风险: ${cell.worst_risk ?? "—"}`
    : `${repoName} — ${cell.month}\n无审查`;

  return (
    <Tooltip title={<span style={{ whiteSpace: "pre-line" }}>{tooltip}</span>}>
      <div
        onClick={onClick}
        style={{
          width: 40,
          height: 40,
          backgroundColor: color,
          borderRadius: 4,
          cursor: cell.review_count > 0 ? "pointer" : "default",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 11,
          color: cell.worst_risk ? "#fff" : "#bbb",
          fontWeight: 600,
          transition: "transform 0.15s",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.transform = "scale(1.15)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.transform = "scale(1)";
        }}
      >
        {cell.review_count > 0 ? cell.review_count : ""}
      </div>
    </Tooltip>
  );
}

interface Props {
  data: HeatmapData | null;
  onCellClick: (repoId: string, month: string) => void;
}

export default function ReviewHeatmap({ data, onCellClick }: Props) {
  if (!data || data.repos.length === 0) {
    return <div style={{ color: "#999", padding: 24, textAlign: "center" }}>暂无审查数据</div>;
  }

  const columns: ColumnsType<HeatmapRepoRow> = [
    {
      title: "仓库",
      dataIndex: "repo_name",
      key: "repo",
      fixed: "left",
      width: 140,
      ellipsis: true,
    },
    ...data.months.map((month) => ({
      title: monthLabel(month),
      key: month,
      width: 56,
      align: "center" as const,
      render: (_: unknown, repo: HeatmapRepoRow) => {
        const cell = repo.cells.find((c) => c.month === month);
        if (!cell) return <div style={{ width: 40, height: 40 }} />;
        return (
          <HeatmapCellView
            cell={cell}
            repoName={repo.repo_name}
            onClick={() => cell.review_count > 0 && onCellClick(repo.repo_id, month)}
          />
        );
      },
    })),
  ];

  return (
    <Table
      dataSource={data.repos}
      rowKey="repo_id"
      columns={columns}
      pagination={false}
      scroll={{ x: "max-content" }}
      size="small"
    />
  );
}
