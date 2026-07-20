import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Loader2 } from "lucide-react";
import type { ReviewLog } from "../types";

const stepLabels: Record<string, string> = {
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
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const displayLogs = expanded ? logs : logs.slice(-MAX_VISIBLE);
  const hiddenCount = logs.length - MAX_VISIBLE;

  const isComplete =
    logs.length > 0 && logs[logs.length - 1].message === "审查完成";
  const isFailed = !logPolling && !isComplete && logs.length > 0;

  const statusColor = isComplete
    ? "text-[var(--severity-low)]"
    : isFailed
      ? "text-destructive"
      : "text-primary";

  return (
    <Card className="mb-6">
      <CardHeader className="pb-2">
        <CardTitle
          className={`flex items-center gap-2 text-base ${statusColor}`}
        >
          {logPolling && !isComplete && (
            <Loader2 className="h-4 w-4 animate-spin" />
          )}
          {isComplete ? "审查完成" : isFailed ? "审查失败" : "审查进行中"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="max-h-[400px] overflow-auto font-mono text-[13px] leading-[1.8]">
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
                  log.level === "error" ? "hsl(var(--destructive))" : undefined,
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
              {log.message}
            </div>
          ))}

          {logPolling && !isComplete && (
            <div className="text-primary mt-1 animate-pulse">...</div>
          )}

          {isComplete && (
            <div className="text-[var(--severity-low)] font-semibold mt-1">
              审查完成
            </div>
          )}

          {isFailed && (
            <div className="text-destructive font-semibold mt-1">审查失败</div>
          )}

          <div ref={bottomRef} />
        </div>
      </CardContent>
    </Card>
  );
}
