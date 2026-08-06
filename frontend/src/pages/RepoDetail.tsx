import { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { Archive, ArchiveRestore, ChevronLeft, RefreshCw, Trash2 } from "lucide-react";
import type { Repo, ReviewTask } from "../types";
import { repoApi } from "../api/repos";
import { reviewApi } from "../api/reviews";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import SubmitReviewModal from "../components/SubmitReviewModal";

const statusVariant: Record<string, "default" | "secondary" | "low" | "destructive"> = {
  done: "low",
  failed: "destructive",
  pending: "secondary",
  running: "default",
};

const statusLabel: Record<string, string> = {
  done: "完成",
  failed: "失败",
  pending: "等待中",
  preparing: "准备审查中",
  running: "进行中",
};

function getErrorMessage(error: unknown, fallback: string) {
  const responseError = error as {
    response?: { data?: { detail?: string } };
    message?: string;
  };
  return responseError.response?.data?.detail || responseError.message || fallback;
}

function getPullRequestLabel(gitUrl: string) {
  return gitUrl.toLowerCase().includes("gitee.com") ? "Gitee PR" : "GitHub PR";
}

function sourceLabel(task: ReviewTask) {
  if (task.source_type === "workspace") return "本地工作区";
  if (task.source_type === "remote_latest") return "远程最新提交";
  if (task.source_type === "remote_commit") return "远程 Commit";
  return task.review_type === "pr" ? "PR" : "远程 Commit";
}

export default function RepoDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [repo, setRepo] = useState<Repo | null>(null);
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [actionPendingId, setActionPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [branches, setBranches] = useState<string[]>([]);
  const [branchError, setBranchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [reviewType, setReviewType] = useState<"local" | "pr">("local");
  const [branch, setBranch] = useState("");
  const [prNumber, setPrNumber] = useState("");
  const [commitHash, setCommitHash] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = async (includeArchived = showArchived) => {
    if (!id) return;
    setLoading(true);
    setLoadError(null);
    setBranchError(null);
    const [repoResult, taskResult, branchResult] = await Promise.allSettled([
      repoApi.get(id),
      reviewApi.list(id, includeArchived),
      repoApi.branches(id),
    ]);

    if (repoResult.status === "fulfilled") {
      setRepo(repoResult.value.data);
    } else {
      setLoadError(getErrorMessage(repoResult.reason, "无法加载仓库信息"));
    }
    if (taskResult.status === "fulfilled") {
      setTasks(taskResult.value.data);
    } else {
      setLoadError((current) => current || getErrorMessage(taskResult.reason, "无法加载审查历史"));
    }
    if (branchResult.status === "fulfilled") {
      setBranches(branchResult.value.data.map((item) => item.name));
    } else {
      setBranchError(getErrorMessage(branchResult.reason, "无法加载分支列表"));
    }
    setLoading(false);
  };

  useEffect(() => {
    void load(showArchived);
  }, [id, showArchived]);

  const manageTask = async (task: ReviewTask, action: "archive" | "restore" | "delete") => {
    if (action === "delete" && !window.confirm("永久删除这条审查记录？报告、日志和变更快照也会一并删除，无法恢复。")) {
      return;
    }
    setActionPendingId(task.id);
    setActionError(null);
    try {
      if (action === "archive") await reviewApi.archive(task.id);
      if (action === "restore") await reviewApi.restore(task.id);
      if (action === "delete") await reviewApi.remove(task.id);
      await load(showArchived);
    } catch (error) {
      setActionError(getErrorMessage(error, "更新审查记录失败"));
    } finally {
      setActionPendingId(null);
    }
  };

  const handleSubmit = async () => {
    if (!id) return;
    if (reviewType === "pr" && !prNumber) {
      setSubmitError("请输入 PR 编号");
      return;
    }
    if (reviewType === "local" && !branch && !commitHash) {
      setSubmitError("请选择审查分支，或输入 Commit Hash");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await reviewApi.submit(id, {
        review_type: reviewType,
        pr_number: reviewType === "pr" ? parseInt(prNumber, 10) : undefined,
        commit_hash: reviewType === "local" && commitHash ? commitHash : undefined,
        branch: reviewType === "local" && branch ? branch : undefined,
      });
      navigate(`/reviews/${response.data.id}`);
    } catch (error) {
      setSubmitError(getErrorMessage(error, "提交审查失败"));
    } finally {
      setSubmitting(false);
    }
  };

  const handleSync = async () => {
    if (!id) return;
    setSyncing(true);
    setBranchError(null);
    try {
      const response = await repoApi.sync(id);
      setBranches(response.data.branches.map((item) => item.name));
      setRepo((current) => current ? {
        ...current,
        default_branch: response.data.default_branch,
        last_synced_at: response.data.checked_at,
        sync_status: response.data.status,
        sync_error: null,
      } : current);
    } catch (error) {
      setBranchError(getErrorMessage(error, "同步远程分支失败"));
    } finally {
      setSyncing(false);
    }
  };

  const handleDeleteRepo = async () => {
    if (!id) return;
    try {
      await repoApi.remove(id);
      navigate("/repos");
    } catch (error) {
      setLoadError(getErrorMessage(error, "删除仓库失败"));
    }
  };

  const selectedMonth = searchParams.get("month");
  const visibleTasks = tasks
    .filter((task) => showArchived ? Boolean(task.archived_at) : !task.archived_at)
    .filter((task) => !selectedMonth || (task.completed_at || task.created_at).slice(0, 7) === selectedMonth);

  if (loading) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/repos")}>
          <ChevronLeft className="h-4 w-4 mr-1" />返回
        </Button>
        <Card><CardContent className="p-6 text-center text-muted-foreground">加载中...</CardContent></Card>
      </div>
    );
  }

  if (loadError || !repo) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/repos")}>
          <ChevronLeft className="h-4 w-4 mr-1" />返回
        </Button>
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6 text-center">
          <div className="font-medium text-destructive">加载失败</div>
          <p className="mt-2 text-sm text-muted-foreground">{loadError || "仓库不存在"}</p>
          <Button className="mt-4" variant="outline" onClick={() => void load()}>重试</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate("/repos")}>
        <ChevronLeft className="h-4 w-4 mr-1" />返回
      </Button>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{repo.name}</h1>
          <p className="mt-1 break-all text-sm text-muted-foreground">{repo.git_url}</p>
        </div>
        <div className="flex w-full gap-2 sm:w-auto">
          <Button variant="outline" className="flex-1 sm:flex-none" onClick={() => void handleSync()} disabled={syncing}>
            <RefreshCw className={`mr-1 h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "同步中..." : "同步远程分支"}
          </Button>
          <Button className="flex-1 sm:flex-none" onClick={() => setReviewModalOpen(true)}>发起审查</Button>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {repo.last_synced_at ? `最近同步：${new Date(repo.last_synced_at).toLocaleString()}` : "尚未同步远程分支"}
      </p>

      <div className="text-sm">
        {confirmDelete ? (
          <span className="inline-flex items-center gap-2">
            确定删除？
            <Button variant="link" size="sm" className="h-auto p-0 text-destructive" onClick={() => void handleDeleteRepo()}>确认</Button>
            <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setConfirmDelete(false)}>取消</Button>
          </span>
        ) : (
          <Button variant="link" size="sm" className="h-auto p-0 text-destructive" onClick={() => setConfirmDelete(true)}>删除仓库</Button>
        )}
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">提交审查</CardTitle></CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
            <div className="min-w-0">
              <label className="text-sm font-medium block mb-1">类型</label>
              <div className="flex rounded-md border h-9">
                <button type="button" className={`flex-1 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:flex-none ${reviewType === "local" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => { setReviewType("local"); setSubmitError(null); }} aria-pressed={reviewType === "local"}>远程 Commit</button>
                <button type="button" className={`flex-1 px-3 text-sm rounded-r-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:flex-none ${reviewType === "pr" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => { setReviewType("pr"); setSubmitError(null); }} aria-pressed={reviewType === "pr"}>{getPullRequestLabel(repo.git_url)}</button>
              </div>
            </div>
            {reviewType === "local" ? (
              <div>
                <label htmlFor="review-branch" className="text-sm font-medium block mb-1">审查分支</label>
                <select id="review-branch" className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm" value={branch} onChange={(event) => setBranch(event.target.value)} disabled={branches.length === 0}>
                  <option value="">选择分支</option>
                  {branches.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
                {branchError && <p className="mt-1 text-xs text-destructive">{branchError}</p>}
              </div>
            ) : (
              <div>
                <label htmlFor="review-pr-number" className="text-sm font-medium block mb-1">PR 编号</label>
                <input id="review-pr-number" type="number" min={1} className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm" value={prNumber} onChange={(event) => setPrNumber(event.target.value)} />
              </div>
            )}
            {reviewType === "local" && (
              <div>
                <label htmlFor="review-commit-hash" className="text-sm font-medium block mb-1">Commit Hash（可选）</label>
                <input id="review-commit-hash" className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm font-mono" value={commitHash} onChange={(event) => setCommitHash(event.target.value)} placeholder="留空审查分支最新提交" />
              </div>
            )}
            <Button className="w-full md:w-auto" onClick={() => void handleSubmit()} disabled={submitting || (reviewType === "local" && branches.length === 0 && !commitHash)}>
              {submitting ? "提交中..." : "提交审查"}
            </Button>
          </div>
          {submitError && <div role="alert" className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{submitError}</div>}
          {reviewType === "local" && !branchError && <p className="mt-3 text-xs text-muted-foreground">选择分支后留空 Commit Hash，将审查该分支当前最新提交。</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <CardTitle className="text-base">审查历史</CardTitle>
            <div className="flex rounded-md border" role="group" aria-label="审查记录范围">
              <button type="button" className={`min-h-9 px-3 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${!showArchived ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setShowArchived(false)} aria-pressed={!showArchived}>当前记录</button>
              <button type="button" className={`min-h-9 border-l px-3 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${showArchived ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setShowArchived(true)} aria-pressed={showArchived}>已归档</button>
            </div>
          </div>
          {selectedMonth && <Button variant="ghost" size="sm" onClick={() => setSearchParams({})}>清除月份筛选</Button>}
        </CardHeader>
        {selectedMonth && <div className="px-6 pb-3 text-sm text-muted-foreground">正在查看 {selectedMonth} 的审查</div>}
        {actionError && <div role="alert" className="mx-6 mb-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{actionError}</div>}
        <CardContent className="p-0">
          <Table className="min-w-[760px]">
            <TableHeader>
              <TableRow>
                <TableHead className="px-6 py-3 text-muted-foreground">类型</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">分支</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">目标</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">状态</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">时间</TableHead>
                <TableHead className="px-6 py-3 text-right text-muted-foreground">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleTasks.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="px-6 py-8 text-center text-muted-foreground">{showArchived ? "暂无已归档记录" : selectedMonth ? "该月份暂无审查记录" : "暂无审查记录"}</TableCell>
                </TableRow>
              ) : (
                visibleTasks.map((task) => (
                  <TableRow key={task.id}>
                    <TableCell className="px-6 py-3">{sourceLabel(task)}</TableCell>
                    <TableCell className="px-6 py-3 font-mono text-sm text-muted-foreground">{task.branch || "—"}</TableCell>
                    <TableCell className="px-6 py-3 text-muted-foreground">{task.pr_number ? `#${task.pr_number}` : (task.head_revision || task.commit_hash)?.slice(0, 7) || "—"}</TableCell>
                    <TableCell className="px-6 py-3"><div className="flex flex-wrap gap-1"><Badge variant={statusVariant[task.status] || "secondary"}>{statusLabel[task.status] || task.status}</Badge>{task.archived_at && <Badge variant="outline">已归档</Badge>}</div></TableCell>
                    <TableCell className="px-6 py-3 text-muted-foreground">{new Date(task.created_at).toLocaleString()}</TableCell>
                    <TableCell className="px-6 py-3 text-right">
                      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
                        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => navigate(`/reviews/${task.id}`)}>查看详情</Button>
                        {task.archived_at ? (
                          <Button variant="link" size="sm" className="h-auto p-0" disabled={actionPendingId === task.id} onClick={() => void manageTask(task, "restore")}><ArchiveRestore className="mr-1 h-3.5 w-3.5" />恢复</Button>
                        ) : (
                            <Button variant="link" size="sm" className="h-auto p-0" disabled={actionPendingId === task.id || task.status === "pending" || task.status === "preparing" || task.status === "running"} onClick={() => void manageTask(task, "archive")}><Archive className="mr-1 h-3.5 w-3.5" />归档</Button>
                        )}
                        <Button variant="link" size="sm" className="h-auto p-0 text-destructive" disabled={actionPendingId === task.id || task.status === "pending" || task.status === "preparing" || task.status === "running"} onClick={() => void manageTask(task, "delete")}><Trash2 className="mr-1 h-3.5 w-3.5" />删除</Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <SubmitReviewModal open={reviewModalOpen} onClose={() => setReviewModalOpen(false)} preSelectedRepoId={id} />
    </div>
  );
}
