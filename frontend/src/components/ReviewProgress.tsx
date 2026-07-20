import { useEffect, useRef, useState } from "react";
import { Card, Button, Typography } from "antd";
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

interface Props {
  logs: ReviewLog[];
  logPolling: boolean;
}

export default function ReviewProgress({ logs, logPolling }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const displayLogs = expanded ? logs : logs.slice(-MAX_VISIBLE);
  const hiddenCount = logs.length - MAX_VISIBLE;

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleTimeString("zh-CN", { hour12: false });
  };

  const isComplete = logs.length > 0 && logs[logs.length - 1].message === "审查完成";
  const isFailed = !logPolling && !isComplete && logs.length > 0;

  return (
    <Card
      title="审查进行中"
      style={{ marginBottom: 24 }}
      headStyle={
        isComplete
          ? { color: "#52c41a" }
          : isFailed
          ? { color: "#ff4d4f" }
          : undefined
      }
    >
      <div
        style={{
          maxHeight: 400,
          overflow: "auto",
          fontFamily: "monospace",
          fontSize: 13,
          lineHeight: 1.8,
        }}
      >
        {hiddenCount > 0 && !expanded && (
          <div style={{ marginBottom: 8 }}>
            <Button
              type="link"
              size="small"
              onClick={() => setExpanded(true)}
              style={{ padding: 0 }}
            >
              [展开全部 {logs.length} 条]
            </Button>
          </div>
        )}

        {displayLogs.map((log) => (
          <div
            key={log.id}
            style={{
              paddingLeft: log.step === "tool_call" ? 24 : 0,
              color: log.level === "error" ? "#ff4d4f" : "#333",
            }}
          >
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {formatTime(log.created_at)}
            </Typography.Text>{" "}
            {log.step !== "tool_call" && (
              <Typography.Text strong style={{ color: "#1677ff" }}>
                [{stepLabels[log.step] || log.step}]
              </Typography.Text>{" "}
            )}
            {log.message}
          </div>
        ))}

        {logPolling && !isComplete && (
          <div style={{ color: "#1677ff", marginTop: 4 }}>...</div>
        )}

        {isComplete && (
          <div style={{ color: "#52c41a", fontWeight: 600, marginTop: 4 }}>
            审查完成
          </div>
        )}

        {isFailed && (
          <div style={{ color: "#ff4d4f", fontWeight: 600, marginTop: 4 }}>
            审查失败
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </Card>
  );
}
