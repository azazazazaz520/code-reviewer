import { useEffect, useState } from "react";
import { Card, Col, Row, Statistic, Table, Tag, Button } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { OverviewStats, ReviewTask, HeatmapData } from "../types";
import { statsApi } from "../api/stats";
import { useNavigate } from "react-router-dom";
import ReviewHeatmap from "../components/ReviewHeatmap";
import SubmitReviewModal from "../components/SubmitReviewModal";

const riskColors: Record<string, string> = {
  low: "green",
  medium: "gold",
  high: "orange",
  critical: "red",
};

export default function Dashboard() {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    statsApi.overview().then((res) => setStats(res.data));
    statsApi.heatmap().then((res) => setHeatmap(res.data)).catch(() => {});
  }, []);

  if (!stats) return <Card loading />;

  const handleCellClick = (repoId: string, _month: string) => {
    navigate(`/repos/${repoId}`);
  };

  const formatTarget = (r: ReviewTask) => {
    if (r.review_type === "pr") {
      return r.pr_number ? `#${r.pr_number}` : "—";
    }
    return r.commit_hash ? r.commit_hash.slice(0, 7) : "—";
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>仪表盘</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          发起审查
        </Button>
      </div>

      {/* 统计卡片 — 三列 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic title="总审查次数" value={stats.total_reviews} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="本月审查" value={stats.reviews_this_month} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="活跃仓库" value={stats.active_repos} />
          </Card>
        </Col>
      </Row>

      {/* 审查活动热力图 */}
      <Card title="审查活动热力图" style={{ marginBottom: 24 }}>
        <ReviewHeatmap data={heatmap} onCellClick={handleCellClick} />
      </Card>

      {/* 最近审查表格 */}
      <Card title="最近审查" style={{ marginBottom: 24 }}>
        <Table<ReviewTask>
          dataSource={stats.recent_reviews}
          rowKey="id"
          pagination={false}
          columns={[
            { title: "仓库", dataIndex: "repo_name", width: 120, ellipsis: true },
            {
              title: "类型",
              dataIndex: "review_type",
              width: 80,
              render: (v: string) => (v === "pr" ? "PR" : "Local"),
            },
            {
              title: "目标",
              dataIndex: "pr_number",
              width: 100,
              render: (_: unknown, r: ReviewTask) => formatTarget(r),
            },
            {
              title: "风险",
              dataIndex: "risk_level",
              width: 100,
              render: (_: unknown, r: ReviewTask) => {
                if (r.risk_level) {
                  return <Tag color={riskColors[r.risk_level]}>{r.risk_level.toUpperCase()}</Tag>;
                }
                if (r.status === "done") {
                  return <Tag>—</Tag>;
                }
                return <Tag color="blue">{r.status === "running" ? "进行中" : r.status}</Tag>;
              },
            },
            {
              title: "时间",
              dataIndex: "created_at",
              render: (v: string) => new Date(v).toLocaleString(),
            },
            {
              title: "操作",
              render: (_: unknown, r: ReviewTask) => (
                <a onClick={() => navigate(`/reviews/${r.id}`)}>查看报告</a>
              ),
            },
          ]}
        />
      </Card>

      {/* 风险分布 */}
      <Card title="风险分布" style={{ marginBottom: 24 }}>
        {Object.entries(stats.risk_distribution).map(([level, count]) => (
          <Tag key={level} color={riskColors[level]}>
            {level}: {count}
          </Tag>
        ))}
        {Object.values(stats.risk_distribution).every((v) => v === 0) && "暂无数据"}
      </Card>

      <SubmitReviewModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
