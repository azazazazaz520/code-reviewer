import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button, Card, Collapse, Descriptions, Space, Tag, Typography, message } from "antd";
import { CopyOutlined } from "@ant-design/icons";
import type { Finding, ReviewLog, ReviewReport, ReviewTask } from "../types";
import { reviewApi } from "../api/reviews";
import ReviewProgress from "../components/ReviewProgress";

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

const riskColors: Record<string, string> = {
  low: "green",
  medium: "gold",
  high: "orange",
  critical: "red",
};

function copyFinding(f: Finding) {
  const text = `[${f.severity.toUpperCase()}] ${f.file}:${f.line} — ${f.title}\n原因：${f.reason}\n建议：${f.suggestion}`;
  navigator.clipboard.writeText(text).then(
    () => message.success("已复制到剪贴板"),
    () => message.error("复制失败"),
  );
}

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<ReviewTask | null>(null);
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [polling, setPolling] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState<string | null>(null);
  const [logs, setLogs] = useState<ReviewLog[]>([]);
  const [logPolling, setLogPolling] = useState(true);

  useEffect(() => {
    if (!id) return;

    const fetchAll = () => {
      reviewApi.status(id).then((r) => setTask(r.data));

      reviewApi.report(id).then((r) => {
        if (r.data.report) setReport(r.data.report);
        if (r.data.status !== "pending" && r.data.status !== "running") {
          setPolling(false);
        }
      });

      reviewApi.logs(id).then((r) => {
        setLogs(r.data);
        // 如果已有最终日志且不再 loading，停止日志轮询
        const hasComplete = r.data.some(
          (l: ReviewLog) => l.message === "审查完成" || l.level === "error" && l.step === "generate_report"
        );
        if (hasComplete) {
          setLogPolling(false);
        }
      });
    };

    fetchAll();
    const interval = setInterval(fetchAll, 2000);

    return () => clearInterval(interval);
  }, [id]);

  const findingsBySeverity = (findings: Finding[]) => {
    const groups: Record<string, Finding[]> = { critical: [], high: [], medium: [], low: [] };
    findings.forEach((f) => groups[f.severity]?.push(f));
    return groups;
  };

  if (!report && polling) return (
    <ReviewProgress logs={logs} logPolling={logPolling} />
  );

  if (!report && !polling && task?.status === "failed") {
    return (
      <>
        <Button onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>← 返回</Button>
        <Card
          title="审查失败"
          style={{ borderColor: "#ff4d4f" }}
          headStyle={{ color: "#ff4d4f" }}
        >
          <Typography.Paragraph type="danger">
            {task.error_message || "未知错误"}
          </Typography.Paragraph>
        </Card>
      </>
    );
  }

  if (!report && !polling && task?.status !== "failed") {
    return (
      <>
        <Button onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>← 返回</Button>
        <Card>未找到报告</Card>
      </>
    );
  }

  if (!report) return null;

  const grouped = findingsBySeverity(report.findings);
  const severityEntries = Object.entries(grouped).filter(([, f]) => f.length > 0);

  // 过滤后的条目
  const filteredEntries = filterSeverity
    ? severityEntries.filter(([s]) => s === filterSeverity)
    : severityEntries;

  return (
    <>
      <Button onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>← 返回</Button>

      {report && logs.length > 0 && !polling && (
        <ReviewProgress logs={logs} logPolling={false} />
      )}

      {/* 风险等级 + 总结 */}
      <Descriptions bordered size="small" style={{ marginBottom: 16 }} column={2}>
        <Descriptions.Item label="风险等级">
          <Tag color={riskColors[report.risk_level]}>{report.risk_level.toUpperCase()}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="总结">{report.summary}</Descriptions.Item>
      </Descriptions>

      {/* 统计数据行 */}
      <Descriptions bordered size="small" style={{ marginBottom: 24 }} column={5}>
        <Descriptions.Item label="发现问题">{report.stats.total_findings}</Descriptions.Item>
        <Descriptions.Item label="涉及文件">{report.stats.impacted_files}</Descriptions.Item>
        <Descriptions.Item label="严重">{report.stats.by_severity.critical || 0}</Descriptions.Item>
        <Descriptions.Item label="高危">{report.stats.by_severity.high || 0}</Descriptions.Item>
        <Descriptions.Item label="中危">{report.stats.by_severity.medium || 0}</Descriptions.Item>
      </Descriptions>

      {/* 严重度过滤条 */}
      <Space style={{ marginBottom: 16 }}>
        <Tag
          color={filterSeverity === null ? "blue" : "default"}
          style={{ cursor: "pointer" }}
          onClick={() => setFilterSeverity(null)}
        >
          📋 全部 ({report.findings.length})
        </Tag>
        {severityEntries.map(([severity, findings]) => (
          <Tag
            key={severity}
            color={filterSeverity === severity ? severityColors[severity] : "default"}
            style={{ cursor: "pointer", opacity: filterSeverity && filterSeverity !== severity ? 0.4 : 1 }}
            onClick={() => setFilterSeverity(filterSeverity === severity ? null : severity)}
          >
            {severityLabels[severity]} ({findings.length})
          </Tag>
        ))}
      </Space>

      {/* Findings 列表 */}
      {filteredEntries.map(([severity, findings]) => (
        <Collapse
          key={severity}
          style={{ marginBottom: 16 }}
          defaultActiveKey={[severity]}
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
                  title={
                    <Space style={{ justifyContent: "space-between", width: "100%" }}>
                      <span>{f.file}:{f.line} — {f.title}</span>
                      <Button
                        type="text"
                        size="small"
                        icon={<CopyOutlined />}
                        onClick={() => copyFinding(f)}
                      />
                    </Space>
                  }
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
      ))}

      {filteredEntries.length === 0 && (
        <Card>该严重度下无发现问题</Card>
      )}
    </>
  );
}
