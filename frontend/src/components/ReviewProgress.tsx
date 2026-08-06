import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Loader2, ChevronDown } from "lucide-react";
import type { ReviewLog } from "../types";
import { formatErrorMessage } from "../lib/error-message";

const stepLabels: Record<string, string> = {
  prepare_source: "准备审查来源",
  load_pr: "获取代码变更",
  collect_context: "收集上下文",
  planning: "规划策略",
  run_reviews: "执行审查",
  reflection: "反思",
  generate_report: "生成报告",
  tool_call: "",
};

const MAX_VISIBLE = 50;

interface ReviewProgressProps {
  logs: ReviewLog[];
  logPolling: boolean;
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("zh-CN", { hour12: false });
}

export default function ReviewProgress({
  logs,
  logPolling,
}: ReviewProgressProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (logPolling) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs.length, logPolling]);

  const isComplete =
    logs.length > 0 && logs[logs.length - 1].message === "审查完成";
  const isFailed = !logPolling && !isComplete && logs.length > 0;

  // When running, show logs; when complete/failed, collapsed by default
  const showLogs = logPolling || expanded;

  const displayLogs = expanded ? logs : logs.slice(-MAX_VISIBLE);
  const hiddenCount = logs.length - MAX_VISIBLE;

  const statusColor = isComplete
    ? "text-severity-low"
    : isFailed
      ? "text-destructive"
      : "text-primary";

  const stepCount = logs.filter((l) => l.step !== "tool_call").length;

  return (
    <Card className="mb-6">
      <CardHeader className="pb-2">
        <CardTitle className={`text-base ${statusColor}`}>
          {logPolling ? (
            <span className="flex items-center gap-2">
              {!isComplete && <Loader2 className="h-4 w-4 animate-spin" />}
              {isComplete ? "审查完成" : "审查进行中"}
            </span>
          ) : (
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
            >
              {isComplete ? "审查完成" : isFailed ? "审查失败" : "审查进行中"}
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

      {showLogs && (
        <CardContent>
          <div className="max-h-[400px] overflow-auto font-mono text-[13px] leading-[1.8]">
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

            <div ref={bottomRef} />
          </div>
        </CardContent>
      )}
    </Card>
  );
}
