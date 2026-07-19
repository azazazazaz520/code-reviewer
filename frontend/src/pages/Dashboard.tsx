import { useEffect, useState } from "react";
import { Card, Col, Row, Statistic, Table, Tag } from "antd";
import type { OverviewStats, ReviewTask } from "../types";
import { statsApi } from "../api/stats";
import { useNavigate } from "react-router-dom";

const severityColors: Record<string, string> = {
  critical: "red",
  high: "orange",
  medium: "gold",
  low: "green",
};

export default function Dashboard() {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    statsApi.overview().then((res) => setStats(res.data));
  }, []);

  if (!stats) return <Card loading />;

  return (
    <>
      <h2>仪表盘</h2>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="总审查次数" value={stats.total_reviews} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="本月审查" value={stats.reviews_this_month} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="平均风险" value={stats.avg_risk_level} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="活跃仓库" value={stats.active_repos} />
          </Card>
        </Col>
      </Row>

      <Card title="最近审查" style={{ marginTop: 24 }}>
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
            { title: "标识", dataIndex: "pr_number", width: 80 },
            {
              title: "风险",
              dataIndex: "status",
              width: 100,
              render: (_: string, r: ReviewTask) => (
                <Tag color={r.status === "done" ? "green" : r.status === "failed" ? "red" : "blue"}>
                  {r.status}
                </Tag>
              ),
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

      <Card title="风险分布" style={{ marginTop: 24 }}>
        {Object.entries(stats.risk_distribution).map(([level, count]) => (
          <Tag key={level} color={severityColors[level]}>
                      {level}: {count}
                    </Tag>
        ))}
        {Object.values(stats.risk_distribution).every((v) => v === 0) && "暂无数据"}
      </Card>
    </>
  );
}
