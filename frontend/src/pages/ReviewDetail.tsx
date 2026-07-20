import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ChevronLeft, TriangleAlert } from "lucide-react";
import type { Finding, ReviewLog, ReviewReport, ReviewTask } from "../types";
import { reviewApi } from "../api/reviews";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Separator } from "../components/ui/separator";
import { Skeleton } from "../components/ui/skeleton";
import FindingCard from "../components/FindingCard";
import ReviewProgress from "../components/ReviewProgress";
import { getSeverityConfig } from "../lib/severity";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const riskVariantMap: Record<string, "critical" | "high" | "medium" | "low"> =
  {
    low: "low",
    medium: "medium",
    high: "high",
    critical: "critical",
  };

function groupFindingsBySeverity(findings: Finding[]) {
  const groups: Record<string, Finding[]> = {
    critical: [],
    high: [],
    medium: [],
    low: [],
  };
  findings.forEach((f) => groups[f.severity]?.push(f));
  return groups;
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
  const [loading, setLoading] = useState(true);

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
        const hasComplete = r.data.some(
          (l: ReviewLog) =>
            l.message === "审查完成" ||
            (l.level === "error" && l.step === "generate_report"),
        );
        if (hasComplete) setLogPolling(false);
      });
    };

    fetchAll();
    setLoading(false);
    const interval = setInterval(fetchAll, 2000);
    return () => clearInterval(interval);
  }, [id]);

  // ── Loading state ──
  if (loading && polling) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // ── Still polling, no report yet ──
  if (!report && polling) {
    return <ReviewProgress logs={logs} logPolling={logPolling} />;
  }

  // ── Failed state ──
  if (!report && !polling && task?.status === "failed") {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-6">
          <h2 className="text-lg font-semibold text-destructive flex items-center gap-2">
            <TriangleAlert className="h-5 w-5" />
            审查失败
          </h2>
          <p className="text-destructive/80 mt-2">
            {task.error_message || "未知错误"}
          </p>
        </div>
      </div>
    );
  }

  // ── No report, not polling, not failed ──
  if (!report && !polling && task?.status !== "failed") {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        <div className="rounded-lg border p-6 text-center text-muted-foreground">
          未找到报告
        </div>
      </div>
    );
  }

  if (!report) return null;

  const grouped = groupFindingsBySeverity(report.findings);
  const severityEntries = Object.entries(grouped).filter(
    ([, f]) => f.length > 0,
  );
  const riskConfig = getSeverityConfig(report.risk_level);
  const RiskIcon = riskConfig.icon;

  const allFindings = report.findings;
  const filteredFindings = filterSeverity
    ? allFindings.filter((f) => f.severity === filterSeverity)
    : allFindings;

  const filteredGrouped = groupFindingsBySeverity(filteredFindings);
  const filteredEntries = Object.entries(filteredGrouped).filter(
    ([, f]) => f.length > 0,
  );

  return (
    <div className="space-y-4">
      {/* Navigation */}
      <Button variant="ghost" onClick={() => navigate(-1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        返回
      </Button>

      {/* Progress log (if not polling) */}
      {report && logs.length > 0 && !polling && (
        <ReviewProgress logs={logs} logPolling={false} />
      )}

      {/* Risk level header */}
      <div className="flex items-center gap-3">
        <Badge variant={riskVariantMap[report.risk_level]}>
          <RiskIcon className="h-3.5 w-3.5" />
          {report.risk_level.toUpperCase()}
        </Badge>
        <span className="text-sm">{report.summary}</span>
      </div>

      <Separator />

      {/* Stats row */}
      <div className="grid grid-cols-5 gap-3">
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold">
            {report.stats.total_findings}
          </div>
          <div className="text-xs text-muted-foreground mt-1">总问题</div>
        </div>
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold">
            {report.stats.impacted_files}
          </div>
          <div className="text-xs text-muted-foreground mt-1">涉及文件</div>
        </div>
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold text-severity-critical">
            {report.stats.by_severity.critical || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">严重</div>
        </div>
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold text-severity-high">
            {report.stats.by_severity.high || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">高危</div>
        </div>
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold text-severity-medium">
            {report.stats.by_severity.medium || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">中危</div>
        </div>
      </div>

      {/* Risk distribution chart */}
      <div className="rounded-lg border bg-card p-4">
        <h3 className="text-sm font-medium mb-3">风险分布</h3>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart
            data={[
              {
                name: "问题数",
                critical: report.stats.by_severity.critical || 0,
                high: report.stats.by_severity.high || 0,
                medium: report.stats.by_severity.medium || 0,
                low: report.stats.by_severity.low || 0,
              },
            ]}
            layout="vertical"
            margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
          >
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" hide />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "6px",
                fontSize: "13px",
              }}
              labelStyle={{ color: "hsl(var(--foreground))" }}
            />
            <Bar
              dataKey="critical"
              stackId="a"
              fill="hsl(var(--severity-critical))"
              radius={[0, 0, 0, 0]}
            />
            <Bar
              dataKey="high"
              stackId="a"
              fill="hsl(var(--severity-high))"
            />
            <Bar
              dataKey="medium"
              stackId="a"
              fill="hsl(var(--severity-medium))"
            />
            <Bar
              dataKey="low"
              stackId="a"
              fill="hsl(var(--severity-low))"
              radius={[4, 4, 4, 4]}
            />
          </BarChart>
        </ResponsiveContainer>
        {/* Chart legend */}
        <div className="flex flex-wrap gap-4 mt-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-severity-critical" />
            严重: {report.stats.by_severity.critical || 0}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-severity-high" />
            高危: {report.stats.by_severity.high || 0}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-severity-medium" />
            中危: {report.stats.by_severity.medium || 0}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-severity-low" />
            低危: {report.stats.by_severity.low || 0}
          </span>
        </div>
      </div>

      {/* Severity filter pills */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setFilterSeverity(null)}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer ${
            filterSeverity === null
              ? "border-primary bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:text-foreground"
          }`}
        >
          全部 ({report.findings.length})
        </button>
        {severityEntries.map(([severity, findings]) => {
          const cfg = getSeverityConfig(severity);
          const Icon = cfg.icon;
          const active = filterSeverity === severity;
          const activeClass =
            severity === "critical"
              ? "border-severity-critical bg-severity-critical/10 text-severity-critical"
              : severity === "high"
                ? "border-severity-high bg-severity-high/10 text-severity-high"
                : severity === "medium"
                  ? "border-severity-medium bg-severity-medium/10 text-severity-medium"
                  : "border-severity-low bg-severity-low/10 text-severity-low";
          return (
            <button
              key={severity}
              onClick={() => setFilterSeverity(active ? null : severity)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer ${
                active
                  ? activeClass
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {cfg.label} ({findings.length})
            </button>
          );
        })}
      </div>

      {/* Findings list */}
      {filteredEntries.length === 0 ? (
        <div className="rounded-lg border p-8 text-center text-muted-foreground">
          该严重度下无发现问题
        </div>
      ) : (
        filteredEntries.map(([severity, findings]) => (
          <div key={severity} className="space-y-2">
            {findings.map((f, i) => (
              <FindingCard
                key={`${f.file}-${f.line}-${i}`}
                finding={f}
                defaultOpen={severity === "critical" || severity === "high"}
              />
            ))}
          </div>
        ))
      )}
    </div>
  );
}
