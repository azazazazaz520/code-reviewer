import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button, Card, Collapse, Descriptions, Space, Tag, Typography } from "antd";
import type { Finding, ReviewReport, ReviewTask } from "../types";
import { reviewApi } from "../api/reviews";

const severityColors: Record<string, string> = {
  critical: "red",
  high: "orange",
  medium: "gold",
  low: "green",
};
const severityLabels: Record<string, string> = {
  critical: "🔴 严重",
  high: "🟠 高危",
  medium: "🟡 中危",
  low: "🟢 低危",
};

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<ReviewTask | null>(null);
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [polling, setPolling] = useState(true);

  useEffect(() => {
    if (!id) return;
    const interval = setInterval(async () => {
      const res = await reviewApi.report(id);
      if (res.data.status === "done" || res.data.status === "failed") {
        setPolling(false);
        clearInterval(interval);
      }
      if (res.data.report) setReport(res.data.report);
    }, 2000);

    reviewApi.status(id).then((r) => setTask(r.data));
    reviewApi.report(id).then((r) => {
      if (r.data.report) setReport(r.data.report);
      if (r.data.status !== "pending" && r.data.status !== "running") setPolling(false);
    });

    return () => clearInterval(interval);
  }, [id]);

  const findingsBySeverity = (findings: Finding[]) => {
    const groups: Record<string, Finding[]> = { critical: [], high: [], medium: [], low: [] };
    findings.forEach((f) => groups[f.severity]?.push(f));
    return groups;
  };

  return (
    <>
      <Button onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>
        ← 返回
      </Button>

      {!report && polling && <Card loading title="审查进行中..." />}
      {!report && !polling && task?.status === "failed" && (
        <Card
          title="审查失败"
          style={{ borderColor: "#ff4d4f" }}
          headStyle={{ color: "#ff4d4f" }}
        >
          <Typography.Paragraph type="danger">
            {task.error_message || "未知错误"}
          </Typography.Paragraph>
        </Card>
      )}
      {!report && !polling && task?.status !== "failed" && <Card>未找到报告</Card>}

      {report && (
        <>
          <Descriptions
            bordered
            size="small"
            style={{ marginBottom: 24 }}
            column={3}
            items={[
              { key: "risk", label: "风险等级", children: <Tag color={severityColors[report.risk_level]}>{report.risk_level.toUpperCase()}</Tag> },
              { key: "findings", label: "发现问题", children: report.stats.total_findings },
              { key: "files", label: "涉及文件", children: report.stats.impacted_files },
            ]}
          />

          <Card title={`📊 ${report.summary}`} style={{ marginBottom: 24 }} />

          {Object.entries(findingsBySeverity(report.findings)).map(
            ([severity, findings]) =>
              findings.length > 0 && (
                <Collapse
                  key={severity}
                  style={{ marginBottom: 16 }}
                  items={[
                    {
                      key: severity,
                      label: (
                        <Tag color={severityColors[severity]}>
                          {severityLabels[severity]} ({findings.length})
                        </Tag>
                      ),
                      children: findings.map((f, i) => (
                        <Card
                          key={i}
                          size="small"
                          style={{ marginBottom: 8 }}
                          title={`${f.file}:${f.line} — ${f.title}`}
                        >
                          <Typography.Paragraph type="secondary">
                            <strong>原因：</strong>
                            {f.reason}
                          </Typography.Paragraph>
                          <Typography.Paragraph type="success">
                            <strong>建议：</strong>
                            {f.suggestion}
                          </Typography.Paragraph>
                        </Card>
                      )),
                    },
                  ]}
                />
              )
          )}
        </>
      )}
    </>
  );
}
