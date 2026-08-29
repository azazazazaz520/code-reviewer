import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Archive, ArchiveRestore, ChevronLeft, Trash2 } from "lucide-react";
import type { Finding, ReviewLog, ReviewReport, ReviewTask } from "../types";
import { reviewApi } from "../api/reviews";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Separator } from "../components/ui/separator";
import { Skeleton } from "../components/ui/skeleton";
import FindingCard from "../components/FindingCard";
import ReviewProgress from "../components/ReviewProgress";
import ReviewHeader from "../components/ReviewHeader";
import ErrorNotice from "../components/ErrorNotice";
import ChangeDiffViewer from "../components/ChangeDiffViewer";
import { getSeverityConfig } from "../lib/severity";
import { formatErrorMessage, formatReviewerName, toUserError, type UserErrorInfo } from "../utils/error-message";
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

const riskBannerClass: Record<string, string> = {
  critical: "border-severity-critical/40 bg-severity-critical/10",
  high: "border-severity-high/40 bg-severity-high/10",
  medium: "border-severity-medium/40 bg-severity-medium/10",
  low: "border-severity-low/40 bg-severity-low/10",
};

function sourceLabel(task: ReviewTask | null) {
  if (task?.source_type === "workspace") return "本地工作区";
  if (task?.source_type === "remote_latest") return "远程最新提交";
  if (task?.source_type === "remote_commit") return "远程指定 Commit";
  return task?.review_type === "pr" ? `PR #${task.pr_number ?? "—"}` : "远程 Commit";
}

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

function groupFindingsByLocation(findings: Finding[]) {
  const groups = new Map<string, Finding[]>();
  for (const f of findings) {
    const key = `${f.file}#${f.line}`;
    const list = groups.get(key);
    if (list) list.push(f);
    else groups.set(key, [f]);
  }
  return [...groups.entries()];
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
  const [loadError, setLoadError] = useState<UserErrorInfo | null>(null);
  const [reportError, setReportError] = useState<UserErrorInfo | null>(null);
  const [actionError, setActionError] = useState<UserErrorInfo | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const taskRef = useRef<ReviewTask | null>(null);
  const reportRef = useRef<ReviewReport | null>(null);

  const fetchAll = useCallback(async () => {
    if (!id) return;
    const [statusResult, reportResult, logsResult] = await Promise.allSettled([
      reviewApi.status(id),
      reviewApi.report(id),
      reviewApi.logs(id),
    ]);

    const status =
      statusResult.status === "fulfilled" ? statusResult.value.data : null;
    const reportResponse =
      reportResult.status === "fulfilled" ? reportResult.value.data : null;

    if (
      statusResult.status === "rejected" &&
      reportResult.status === "rejected" &&
      logsResult.status === "rejected"
    ) {
      setLoading(false);
      if (!taskRef.current && !reportRef.current) {
        setLoadError(toUserError(statusResult.reason, "无法读取审查状态，请检查后端服务后重试"));
      }
      return;
    }

    if (status) {
      taskRef.current = status;
      setTask(status);
    }

    if (reportResponse?.report) {
      reportRef.current = reportResponse.report;
      setReport(reportResponse.report);
      setReportError(null);
    }

    const terminalStatus = status?.status ?? reportResponse?.status;
    const isTerminal =
      terminalStatus !== undefined &&
      terminalStatus !== "pending" &&
      terminalStatus !== "preparing" &&
      terminalStatus !== "running";

    if (isTerminal) {
      setPolling(false);
      setLogPolling(false);
      if (reportResult.status === "rejected") {
        setReportError(toUserError(reportResult.reason, "审查已结束，但报告读取失败，请稍后重试"));
      } else if (!reportResponse?.report && terminalStatus === "done") {
        setReportError(toUserError(null, "审查已结束，但报告记录不可用"));
      }
    }

    if (logsResult.status === "fulfilled") {
      setLogs(logsResult.value.data);
      const hasComplete = logsResult.value.data.some(
        (l: ReviewLog) =>
          l.message === "审查完成" ||
          (l.level === "error" && l.step === "generate_report"),
      );
      if (hasComplete) setLogPolling(false);
    }
    setLoading(false);
  }, [id]);

  // Initial fetch
  useEffect(() => {
    if (!id) {
      setLoading(false);
      setLoadError(toUserError(null, "缺少审查任务 ID"));
      return;
    }
    setTask(null);
    setReport(null);
    taskRef.current = null;
    reportRef.current = null;
    setLogs([]);
    setPolling(true);
    setLogPolling(true);
    setLoadError(null);
    setReportError(null);
    setLoading(true);
    void fetchAll();
  }, [id, fetchAll]);

  // Polling: only when status or logs are still pending
  useEffect(() => {
    if (!id || (!polling && !logPolling)) return;
    const interval = setInterval(fetchAll, 2000);
    return () => clearInterval(interval);
  }, [id, polling, logPolling, fetchAll]);

  // ── Loading state ──
  const retry = () => {
    setLoading(true);
    setLoadError(null);
    setReportError(null);
    setPolling(true);
    setLogPolling(true);
    void fetchAll();
  };

  const page = (content: ReactNode, fallbackStatus?: string) => (
    <div className="space-y-4">
      <ReviewHeader task={task} report={report} fallbackStatus={fallbackStatus} />
      {content}
    </div>
  );

  const manageReview = async (action: "archive" | "restore" | "delete") => {
    if (!task) return;
    if (action === "delete" && !window.confirm("永久删除这条审查记录？报告、日志和变更快照也会一并删除，无法恢复。")) {
      return;
    }
    setActionPending(true);
    setActionError(null);
    try {
      if (action === "archive") await reviewApi.archive(task.id);
      if (action === "restore") await reviewApi.restore(task.id);
      if (action === "delete") {
        await reviewApi.remove(task.id);
        navigate(-1);
        return;
      }
      const refreshed = await reviewApi.status(task.id);
      taskRef.current = refreshed.data;
      setTask(refreshed.data);
    } catch (error) {
      setActionError(toUserError(error, "更新审查记录失败"));
    } finally {
      setActionPending(false);
    }
  };

  if (loading) {
    return page(
      <>
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </>,
      "loading",
    );
  }

  // ── Still polling, no report yet ──
  if (!report && polling) {
    return page(<ReviewProgress logs={logs} logPolling={logPolling} />);
  }

  // ── Failed state ──
  if (!report && !polling && task?.status === "failed") {
    return page(
      <>
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        <ErrorNotice
          title="审查失败"
          error={toUserError(task.error_message, "审查失败，请查看审查日志后重试")}
          onRetry={retry}
        />
      </>,
      "failed",
    );
  }

  if (!report && !polling && reportError) {
    return page(
      <>
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        <ErrorNotice title="报告不可用" error={reportError} onRetry={retry} />
      </>,
      "unavailable",
    );
  }

  if (loadError && !task && !report) {
    return page(
      <>
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        <ErrorNotice title="审查状态不可用" error={loadError} onRetry={retry} />
      </>,
      "unavailable",
    );
  }

  // ── No report, not polling, not failed ──
  if (!report && !polling && task?.status !== "failed") {
    return page(
      <>
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        <div className="rounded-lg border p-6 text-center text-muted-foreground">
          未找到报告
        </div>
      </>,
      "unavailable",
    );
  }

  if (!report) return page(<ErrorNotice title="报告不可用" error={toUserError(null, "当前没有可展示的报告")} onRetry={retry} />, "unavailable");

  const grouped = groupFindingsBySeverity(report.findings);
  const severityEntries = Object.entries(grouped).filter(
    ([, f]) => f.length > 0,
  );
  const riskConfig = getSeverityConfig(report.risk_level);
  const RiskIcon = riskConfig.icon;
  const attentionChecks = (report.checks ?? []).filter(
    (check) => check.status !== "pass",
  );
  const blockingChecks = attentionChecks.filter(
    (check) =>
      check.status === "error" ||
      check.status === "fail" ||
      check.name.startsWith("reviewer_"),
  );
  const diagnosticChecks = attentionChecks.filter(
    (check) =>
      !blockingChecks.includes(check) &&
      check.name !== "finding_context" &&
      check.name !== "finding_gate",
  );
  const contextFindingCount = report.quality?.reviewer_context_findings ?? 0;
  const filteredFindingCount = report.quality?.filtered_findings ?? 0;
  const diagnosticCount =
    diagnosticChecks.length + contextFindingCount + filteredFindingCount;
  const reviewerOutputs = Object.entries(report.reviewer_outputs ?? {});

  const allFindings = report.findings;
  const filteredFindings = filterSeverity
    ? allFindings.filter((f) => f.severity === filterSeverity)
    : allFindings;

  const filteredGrouped = groupFindingsBySeverity(filteredFindings);
  const filteredEntries = Object.entries(filteredGrouped).filter(
    ([, f]) => f.length > 0,
  );

  return page(
    <div className="review-report-enter space-y-4">
      {/* Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        {task && (
          <div className="flex flex-wrap items-center gap-2">
            {task.archived_at ? (
              <Button variant="outline" size="sm" className="min-h-11 sm:min-h-0" disabled={actionPending} onClick={() => void manageReview("restore")}><ArchiveRestore className="mr-1 h-4 w-4" />恢复记录</Button>
            ) : (
              <Button variant="outline" size="sm" className="min-h-11 sm:min-h-0" disabled={actionPending || task.status === "pending" || task.status === "preparing" || task.status === "running"} onClick={() => void manageReview("archive")}><Archive className="mr-1 h-4 w-4" />归档记录</Button>
            )}
            <Button variant="destructive" size="sm" className="min-h-11 sm:min-h-0" disabled={actionPending || task.status === "pending" || task.status === "preparing" || task.status === "running"} onClick={() => void manageReview("delete")}><Trash2 className="mr-1 h-4 w-4" />永久删除</Button>
          </div>
        )}
      </div>
      {actionError && <ErrorNotice error={actionError} compact />}

      {/* Progress log (if not polling) */}
      {report && logs.length > 0 && !polling && (
        <ReviewProgress logs={logs} logPolling={false} />
      )}

      {/* Risk level header */}
      <div
        className={`rounded-lg border p-4 ${riskBannerClass[report.risk_level] ?? "bg-card"}`}
      >
        <Badge variant={riskVariantMap[report.risk_level]}>
          <RiskIcon className="h-3.5 w-3.5" />
          {report.risk_level.toUpperCase()}
        </Badge>
        <p className="mt-2 text-sm leading-6">{report.summary}</p>
      </div>

      {task && (
        <div className="rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            <span>来源：{sourceLabel(task)}</span>
            {task.base_revision && <span>基准：<code>{task.base_revision.slice(0, 12)}</code></span>}
            {task.head_revision && <span>目标：<code>{task.head_revision.slice(0, 12)}</code></span>}
          </div>
          {task.source_type === "workspace" && task.workspace_stats_json && (
            <div className="mt-1 text-xs">工作区快照：{task.workspace_stats_json}</div>
          )}
        </div>
      )}

      <ChangeDiffViewer changes={report.changes} />

      {blockingChecks.length > 0 && (
        <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <h3 className="text-sm font-medium mb-2">需要关注</h3>
          <div className="space-y-2 text-sm">
            {blockingChecks.map((check) => (
              <div key={check.name} className="flex items-start gap-2">
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-destructive" />
                <div>
                  <div className="font-medium">{formatReviewerName(check.name.replace(/^reviewer_/, ""))}</div>
                  <div className="text-muted-foreground">{formatErrorMessage(check.message)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {diagnosticCount > 0 && (
        <details className="rounded-lg border bg-card">
          <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-sm font-medium">
            <span>审查诊断</span>
            <span className="text-xs font-normal text-muted-foreground">{diagnosticCount} 项需复核</span>
          </summary>
          <div className="space-y-2 border-t px-4 py-3 text-sm">
            {contextFindingCount > 0 && (
              <p className="text-muted-foreground">
                {contextFindingCount} 条意见出现在修改文件的相邻代码中，请确认是否与本次提交相关联。
              </p>
            )}
            {filteredFindingCount > 0 && (
              <p className="text-muted-foreground">
                {filteredFindingCount} 条候选意见未通过证据门槛，未计入最终结果。
              </p>
            )}
            {diagnosticChecks.map((check) => (
              <div key={check.name} className="flex items-start gap-2 text-muted-foreground">
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-severity-medium" />
                <div>
                  <div className="font-medium text-foreground">{formatReviewerName(check.name.replace(/^reviewer_/, ""))}</div>
                  <div>{formatErrorMessage(check.message)}</div>
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      {reviewerOutputs.length > 0 && (
        <details className="rounded-lg border bg-card">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
            查看 Reviewer 原始输出与候选意见
          </summary>
          <div className="space-y-4 border-t px-4 py-4">
            {reviewerOutputs.map(([reviewerName, trace]) => (
              <section key={reviewerName} className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-medium">{formatReviewerName(reviewerName)}</h3>
                  <span className="text-xs text-muted-foreground">
                    候选意见 {trace.candidate_findings.length} 条
                  </span>
                </div>
                {trace.error_message && (
                  <p className="text-sm text-destructive">{formatErrorMessage(trace.error_message)}</p>
                )}
                {trace.attempts.map((attempt, index) => (
                  <div key={`${attempt.stage}-${index}`} className="space-y-1">
                    <div className="text-xs font-medium text-muted-foreground">
                      {attempt.stage === "format_repair" ? "格式修复输出" : "原始输出"}
                      {attempt.truncated ? "（已截断）" : ""}
                    </div>
                    <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">
                      {attempt.output || "（空输出）"}
                    </pre>
                  </div>
                ))}
                {trace.candidate_findings.length > 0 && (
                  <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">
                    {JSON.stringify(trace.candidate_findings, null, 2)}
                  </pre>
                )}
              </section>
            ))}
          </div>
        </details>
      )}

      <Separator />

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
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
                backgroundColor: "var(--card)",
                border: "1px solid var(--border)",
                borderRadius: "6px",
                fontSize: "13px",
              }}
              labelStyle={{ color: "var(--foreground)" }}
            />
            <Bar
              dataKey="critical"
              stackId="a"
              fill="var(--severity-critical)"
              radius={[0, 0, 0, 0]}
            />
            <Bar
              dataKey="high"
              stackId="a"
              fill="var(--severity-high)"
            />
            <Bar
              dataKey="medium"
              stackId="a"
              fill="var(--severity-medium)"
            />
            <Bar
              dataKey="low"
              stackId="a"
              fill="var(--severity-low)"
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
          type="button"
          onClick={() => setFilterSeverity(null)}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
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
              type="button"
              onClick={() => setFilterSeverity(active ? null : severity)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                active
                  ? activeClass
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
              aria-pressed={active}
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
            {groupFindingsByLocation(findings).map(([locationKey, group]) => (
              <div key={locationKey} className="space-y-1">
                <FindingCard
                  finding={group[0]}
                  defaultOpen={severity === "critical" || severity === "high"}
                />
                {group.length > 1 && (
                  <details className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
                    <summary className="cursor-pointer text-xs">
                      同位置另有 {group.length - 1} 条相关意见
                    </summary>
                    <div className="mt-2 space-y-1">
                      {group.slice(1).map((f, i) => (
                        <FindingCard
                          key={`${locationKey}-${i}`}
                          finding={f}
                          defaultOpen={false}
                        />
                      ))}
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
        ))
      )}
    </div>,
  );
}
