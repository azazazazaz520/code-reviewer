import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Check, CircleAlert, ChevronDown, Loader2 } from "lucide-react";
import type { ReviewLog } from "../types";
import { formatErrorMessage } from "../utils/error-message";

const reviewSteps = [
  { key: "prepare_source", label: "准备审查来源" },
  { key: "load_pr", label: "获取代码变更" },
  { key: "collect_context", label: "收集上下文" },
  { key: "planning", label: "规划策略" },
  { key: "run_reviews", label: "执行审查" },
  { key: "reflection", label: "反思" },
  { key: "generate_report", label: "生成报告" },
] as const;

const stepLabels: Record<string, string> = {
  ...Object.fromEntries(reviewSteps.map((step) => [step.key, step.label])),
  tool_call: "",
};

const MAX_VISIBLE = 50;
type TimelineStatus = "waiting" | "running" | "done" | "failed";
type TimelineStepStatus = "pending" | "active" | "done" | "failed";

interface ReviewTimeline {
  status: TimelineStatus;
  activeIndex: number;
  completedCount: number;
  progress: number;
  steps: Array<{
    key: string;
    label: string;
    status: TimelineStepStatus;
    detail: string;
  }>;
}

interface ReviewProgressProps {
  logs: ReviewLog[];
  logPolling: boolean;
  taskStatus?: string;
  onCancel?: () => void;
  cancelPending?: boolean;
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("zh-CN", { hour12: false });
}

function stepIndex(step: string | undefined) {
  if (!step) return -1;
  return reviewSteps.findIndex((item) => item.key === step);
}

function summarizeLogMessage(message: string) {
  const normalized = message.replace(/\s+/g, " ").trim();
  return normalized.length > 56 ? `${normalized.slice(0, 53)}...` : normalized;
}

function buildReviewTimeline(
  logs: ReviewLog[],
  isComplete: boolean,
  isFailed: boolean,
): ReviewTimeline {
  const knownLogs = logs.filter((log) => stepIndex(log.step) >= 0);
  const latestLog = knownLogs[knownLogs.length - 1];
  const latestError = [...knownLogs]
    .reverse()
    .find((log) => log.level === "error");
  const status: TimelineStatus = isComplete
    ? "done"
    : isFailed
      ? "failed"
      : logs.length === 0
        ? "waiting"
        : "running";
  const activeIndex = status === "done"
    ? reviewSteps.length - 1
    : stepIndex(latestLog?.step) >= 0
      ? stepIndex(latestLog?.step)
      : 0;
  const failedIndex = status === "failed"
    ? stepIndex(latestError?.step) >= 0
      ? stepIndex(latestError?.step)
      : activeIndex
    : -1;
  const currentIndex = status === "failed" ? failedIndex : activeIndex;
  const completedCount = status === "done"
    ? reviewSteps.length
    : Math.max(0, currentIndex);
  const progress = status === "done"
    ? 1
    : completedCount / (reviewSteps.length - 1);

  const steps = reviewSteps.map((step, index) => {
    let stepStatus: TimelineStepStatus = "pending";
    if (status === "done" || index < currentIndex) stepStatus = "done";
    else if (status === "failed" && index === failedIndex) stepStatus = "failed";
    else if (index === activeIndex) stepStatus = "active";

    let detail = "等待前序阶段";
    if (stepStatus === "done") detail = "已完成";
    if (stepStatus === "failed") {
      detail = latestError?.step === step.key
        ? summarizeLogMessage(formatErrorMessage(latestError.message))
        : "执行失败";
    }
    if (stepStatus === "active") {
      detail = status === "waiting"
        ? "等待执行"
        : latestLog?.step === step.key
          ? summarizeLogMessage(formatErrorMessage(latestLog.message))
          : "执行中";
    }

    return { ...step, status: stepStatus, detail };
  });

  return { status, activeIndex, completedCount, progress, steps };
}

export default function ReviewProgress({
  logs,
  logPolling,
  taskStatus,
  onCancel,
  cancelPending = false,
}: ReviewProgressProps) {
  const logContainerRef = useRef<HTMLDivElement>(null);
  const previousLogCountRef = useRef(logs.length);
  const didMountRef = useRef(false);
  const [expanded, setExpanded] = useState(false);
  const [following, setFollowing] = useState(true);
  const [newLogsAvailable, setNewLogsAvailable] = useState(false);

  useEffect(() => {
    const previousCount = previousLogCountRef.current;
    previousLogCountRef.current = logs.length;
    if (!didMountRef.current) {
      didMountRef.current = true;
      if (logPolling && following && logContainerRef.current) {
        logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      }
      return;
    }
    if (logs.length <= previousCount) return;

    const container = logContainerRef.current;
    if (following && container) {
      container.scrollTop = container.scrollHeight;
      setNewLogsAvailable(false);
    } else if (!following) {
      setNewLogsAvailable(true);
    }
  }, [logs.length, logPolling, following]);

  const handleLogScroll = () => {
    const container = logContainerRef.current;
    if (!container) return;
    const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= 32;
    setFollowing(atBottom);
    if (atBottom) setNewLogsAvailable(false);
  };

  const scrollToBottom = () => {
    const container = logContainerRef.current;
    if (!container) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (typeof container.scrollTo === "function") {
      container.scrollTo({ top: container.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
    } else {
      container.scrollTop = container.scrollHeight;
    }
    setFollowing(true);
    setNewLogsAvailable(false);
  };

  const isComplete =
    logs.length > 0 && logs[logs.length - 1].message === "审查完成";
  const isCancelled = ["cancelling", "cancelled"].includes(taskStatus ?? "");
  const isFailed = !isCancelled && !logPolling && !isComplete && logs.length > 0;

  const timeline = buildReviewTimeline(logs, isComplete, isFailed);
  const timelineStatusText = timeline.status === "done"
    ? "审查完成"
    : isCancelled
      ? "审查已取消"
    : timeline.status === "failed"
      ? "审查失败"
      : timeline.status === "waiting"
        ? "等待执行"
        : "审查进行中";
  const currentStep = timeline.steps[timeline.activeIndex];
  const timelineDetail = timeline.status === "done"
    ? "所有阶段已完成"
    : isCancelled
      ? "已停止继续请求模型和工具"
    : timeline.status === "failed"
      ? `失败阶段：${currentStep?.label ?? "未知阶段"}`
      : `当前阶段：${currentStep?.label ?? "准备审查来源"}`;

  // 审查执行时展开日志，结束后默认折叠。
  const showLogs = logPolling || expanded;
  const canCancel = Boolean(
    onCancel && ["pending", "preparing", "running"].includes(taskStatus ?? ""),
  );

  const displayLogs = expanded ? logs : logs.slice(-MAX_VISIBLE);
  const hiddenCount = logs.length - MAX_VISIBLE;

  const statusColor = isComplete
    ? "text-severity-low"
    : isFailed
      ? "text-destructive"
      : "text-primary";

  const stepCount = logs.filter((l) => l.step !== "tool_call").length;
  const statusText = isComplete
    ? "审查完成"
    : isCancelled
    ? "审查已取消"
    : isFailed
      ? "审查失败"
      : logs.length === 0
        ? "审查任务已提交，等待执行"
        : "审查进行中";

  return (
    <Card className="mb-6">
      <div className="sr-only" role="status" aria-live="polite">{statusText}</div>
      <CardHeader className="pb-2">
        <CardTitle className={`text-base ${statusColor}`}>
          {logPolling ? (
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2">{timelineStatusText}</span>
              {canCancel && (
                <Button
                  variant="destructive"
                  size="sm"
                  className="min-h-9 shrink-0"
                  onClick={onCancel}
                  disabled={cancelPending}
                >
                  {cancelPending ? "正在停止..." : "停止审查"}
                </Button>
              )}
            </div>
          ) : (
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
            >
              {isComplete ? "审查完成" : isCancelled ? "审查已取消" : isFailed ? "审查失败" : "审查进行中"}
              <span className="text-xs text-muted-foreground font-normal ml-2">
                {stepCount} 个步骤 · {logs.length} 条日志
              </span>
              <ChevronDown
                className={`h-4 w-4 ml-auto text-muted-foreground transition-transform duration-150 ${
                  expanded ? "rotate-180" : ""
                }`}
              />
            </button>
          )}
        </CardTitle>
      </CardHeader>

      <section className="review-progress-timeline-section" aria-labelledby="review-progress-timeline-title">
        <h3 id="review-progress-timeline-title" className="sr-only">审查阶段进度</h3>
        <div
          className="review-progress-timeline"
          role="progressbar"
          aria-label="审查阶段进度"
          aria-valuemin={0}
          aria-valuemax={reviewSteps.length}
          aria-valuenow={timeline.completedCount}
        >
          <div className="review-progress-timeline-list-wrap">
            <div className="review-progress-timeline-track" aria-hidden="true">
              <div
                className={`review-progress-timeline-track-fill ${timeline.status === "failed" ? "review-progress-timeline-track-fill-failed" : ""}`}
                style={{ transform: `scaleY(${Math.min(timeline.progress, 1)})` }}
              />
            </div>
            <ol className="review-progress-timeline-list">
              {timeline.steps.map((step) => (
                <li
                  key={step.key}
                  className="review-progress-timeline-step"
                  data-status={step.status}
                  aria-current={step.status === "active" ? "step" : undefined}
                >
                  <div className="review-progress-timeline-node" aria-hidden="true">
                    {step.status === "done" && <Check className="h-3.5 w-3.5" />}
                    {step.status === "failed" && <CircleAlert className="h-3.5 w-3.5" />}
                    {step.status === "active" && (
                      <Loader2 className="review-progress-timeline-spinner h-3.5 w-3.5 animate-spin" />
                    )}
                    {step.status === "pending" && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                  </div>
                  <div className="review-progress-timeline-step-copy">
                    <span className="review-progress-timeline-step-label">{step.label}</span>
                    <span className="review-progress-timeline-step-detail">{step.detail}</span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
          <div className="review-progress-timeline-footer">
            <span>{timeline.completedCount} / {reviewSteps.length} 个阶段已完成</span>
            <span>{timelineDetail}</span>
          </div>
        </div>
      </section>

      {showLogs && (
        <CardContent>
          {!following && newLogsAvailable && (
            <Button variant="outline" size="sm" className="mb-2 min-h-9" onClick={scrollToBottom}>
              有新日志，回到底部
            </Button>
          )}
          <div
            id="review-execution-log"
            ref={logContainerRef}
            className="max-h-[400px] overflow-auto font-mono text-[13px] leading-[1.8]"
            role="log"
            aria-label="审查执行日志"
            aria-live="off"
            tabIndex={0}
            onScroll={handleLogScroll}
          >
            {logs.length === 0 && (
              <div className="py-4 font-sans text-sm text-muted-foreground">
                审查任务已提交，正在等待执行日志...
              </div>
            )}
            {hiddenCount > 0 && !expanded && (
              <div className="mb-2">
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-muted-foreground"
                  onClick={() => setExpanded(true)}
                >
                  展开全部 {logs.length} 条
                </Button>
              </div>
            )}

            {displayLogs.map((log) => (
              <div
                key={log.id}
                className={log.step === "tool_call" ? "pl-6" : ""}
                style={{
                  color:
                    log.level === "error"
                      ? "hsl(var(--destructive))"
                      : undefined,
                }}
              >
                <span className="text-[11px] text-muted-foreground">
                  {formatTime(log.created_at)}
                </span>{" "}
                {log.step !== "tool_call" && (
                  <span className="font-semibold text-primary">
                    [{stepLabels[log.step] || log.step}]
                  </span>
                )}{" "}
                {log.level === "error" ? formatErrorMessage(log.message) : log.message}
              </div>
            ))}

            {logPolling && !isComplete && (
              <div className="text-primary mt-1 animate-pulse">...</div>
            )}

          </div>
        </CardContent>
      )}
    </Card>
  );
}
