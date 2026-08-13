import type { ReviewReport, ReviewTask } from "../types";
import { Badge } from "./ui/badge";

const statusLabels: Record<string, string> = {
  loading: "加载中",
  pending: "等待执行",
  preparing: "准备中",
  running: "审查进行中",
  done: "已完成",
  failed: "审查失败",
  unavailable: "报告不可用",
};

function sourceLabel(task: ReviewTask | null) {
  if (task?.source_type === "workspace") return "本地工作区";
  if (task?.source_type === "remote_latest") return "远程最新提交";
  if (task?.source_type === "remote_commit") return "远程指定 Commit";
  if (task?.review_type === "pr") return `PR #${task.pr_number ?? "—"}`;
  if (task) return "远程 Commit";
  return "来源待获取";
}

function targetLabel(task: ReviewTask | null) {
  if (!task) return "目标待获取";
  if (task.pr_number) return `PR #${task.pr_number}`;
  const revision = task.head_revision || task.commit_hash;
  return revision ? revision.slice(0, 12) : "目标待获取";
}

function statusLabel(task: ReviewTask | null, report: ReviewReport | null, fallbackStatus?: string) {
  const status = task?.status || fallbackStatus || (report ? "done" : "loading");
  return statusLabels[status] || status;
}

interface ReviewHeaderProps {
  task: ReviewTask | null;
  report: ReviewReport | null;
  fallbackStatus?: string;
}

export default function ReviewHeader({ task, report, fallbackStatus }: ReviewHeaderProps) {
  return (
    <header className="rounded-lg border bg-card px-4 py-4 sm:px-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Review Workbench</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight">代码审查</h1>
          <p className="mt-1 truncate text-sm text-muted-foreground" title={task?.repo_name || undefined}>
            仓库：{task?.repo_name || "仓库信息待获取"}
          </p>
        </div>
        <Badge variant={task?.status === "failed" || fallbackStatus === "unavailable" ? "destructive" : "secondary"}>
          {statusLabel(task, report, fallbackStatus)}
        </Badge>
      </div>
      <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm text-muted-foreground sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs">来源</dt>
          <dd className="mt-0.5 text-foreground">{sourceLabel(task)}</dd>
        </div>
        <div>
          <dt className="text-xs">目标 Revision / PR</dt>
          <dd className="mt-0.5 break-all font-mono text-foreground">{targetLabel(task)}</dd>
        </div>
        <div>
          <dt className="text-xs">分支</dt>
          <dd className="mt-0.5 break-all font-mono text-foreground">{task?.branch || "分支待获取"}</dd>
        </div>
        <div>
          <dt className="text-xs">审查状态</dt>
          <dd className="mt-0.5 text-foreground">{statusLabel(task, report, fallbackStatus)}</dd>
        </div>
      </dl>
    </header>
  );
}
