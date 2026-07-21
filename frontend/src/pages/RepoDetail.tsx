import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
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
  running: "进行中",
};

export default function RepoDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [repo, setRepo] = useState<Repo | null>(null);
  const [tasks, setTasks] = useState<ReviewTask[]>([]);

  /* form state */
  const [reviewType, setReviewType] = useState<"local" | "pr">("local");
  const [prNumber, setPrNumber] = useState("");
  const [commitHash, setCommitHash] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = async () => {
    if (!id) return;
    const [r, t] = await Promise.all([repoApi.get(id), reviewApi.list(id)]);
    setRepo(r.data);
    setTasks(t.data);
  };

  useEffect(() => { load(); }, [id]);

  const handleSubmit = async () => {
    if (!id) return;
    setSubmitting(true);
    try {
      await reviewApi.submit(id, {
        review_type: reviewType,
        pr_number: reviewType === "pr" && prNumber ? parseInt(prNumber) : undefined,
        commit_hash: reviewType === "local" && commitHash ? commitHash : undefined,
      });
      setPrNumber("");
      setCommitHash("");
      load();
    } catch {
      /* ignore */
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteRepo = async () => {
    if (!id) return;
    await repoApi.remove(id);
    navigate("/repos");
  };

  if (!repo) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/repos")}>
          <ChevronLeft className="h-4 w-4 mr-1" />返回
        </Button>
        <Card><CardContent className="p-6 text-center text-muted-foreground">加载中...</CardContent></Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate("/repos")}>
        <ChevronLeft className="h-4 w-4 mr-1" />返回
      </Button>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">{repo.name}</h1>
        <Button className="w-full sm:w-auto" onClick={() => setReviewModalOpen(true)}>发起审查</Button>
      </div>

      <p className="break-all text-sm text-muted-foreground">
        {repo.git_url}
        {confirmDelete ? (
          <span className="mt-2 inline-flex items-center gap-2 sm:ml-4 sm:mt-0">
            确定删除？{" "}
            <Button variant="link" size="sm" className="h-auto p-0 text-destructive" onClick={handleDeleteRepo}>确认</Button>
            {" / "}
            <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setConfirmDelete(false)}>取消</Button>
          </span>
        ) : (
          <Button variant="link" size="sm" className="h-auto p-0 text-destructive ml-4" onClick={() => setConfirmDelete(true)}>删除仓库</Button>
        )}
      </p>

      {/* Review form */}
      <Card>
        <CardHeader><CardTitle className="text-base">提交审查</CardTitle></CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-[auto_1fr_auto] md:items-end">
            <div className="min-w-0">
              <label className="text-sm font-medium block mb-1">类型</label>
              <div className="flex rounded-md border h-9">
                <button
                  type="button"
                  className={`flex-1 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:flex-none ${reviewType === "local" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                  onClick={() => setReviewType("local")}
                  aria-pressed={reviewType === "local"}
                >
                  Local Commit
                </button>
                <button
                  type="button"
                  className={`flex-1 px-3 text-sm rounded-r-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:flex-none ${reviewType === "pr" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                  onClick={() => setReviewType("pr")}
                  aria-pressed={reviewType === "pr"}
                >
                  GitHub PR
                </button>
              </div>
            </div>
            {reviewType === "pr" && (
              <div>
                <label className="text-sm font-medium block mb-1">PR 编号</label>
                <input
                  type="number"
                  min={1}
                  className="flex h-9 w-28 rounded-md border bg-background px-3 py-1 text-sm"
                  value={prNumber}
                  onChange={(e) => setPrNumber(e.target.value)}
                />
              </div>
            )}
            {reviewType === "local" && (
              <div>
                <label className="text-sm font-medium block mb-1">Commit Hash</label>
                <input
                  className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm font-mono md:w-44"
                  value={commitHash}
                  onChange={(e) => setCommitHash(e.target.value)}
                  placeholder="留空使用 HEAD"
                />
              </div>
            )}
            <Button className="w-full md:w-auto" onClick={handleSubmit} disabled={submitting}>
              {submitting ? "提交中..." : "提交审查"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Review history */}
      <Card>
        <CardHeader><CardTitle className="text-base">审查历史</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table className="min-w-[640px]">
            <TableHeader>
              <TableRow>
                <TableHead className="px-6 py-3 text-muted-foreground">类型</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">标识</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">状态</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">时间</TableHead>
                <TableHead className="px-6 py-3 text-right text-muted-foreground">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tasks.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="px-6 py-8 text-center text-muted-foreground">暂无审查记录</TableCell>
                </TableRow>
              ) : (
                tasks.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="px-6 py-3">{t.review_type === "pr" ? "PR" : "Local"}</TableCell>
                    <TableCell className="px-6 py-3 text-muted-foreground">
                      {t.pr_number ? `#${t.pr_number}` : t.commit_hash?.slice(0, 7) || "—"}
                    </TableCell>
                    <TableCell className="px-6 py-3">
                      <Badge variant={statusVariant[t.status] || "secondary"}>
                        {statusLabel[t.status] || t.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="px-6 py-3 text-muted-foreground">
                      {new Date(t.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="px-6 py-3 text-right">
                      {t.status === "done" && (
                        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => navigate(`/reviews/${t.id}`)}>
                          查看报告
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <SubmitReviewModal
        open={reviewModalOpen}
        onClose={() => setReviewModalOpen(false)}
        preSelectedRepoId={id}
      />
    </div>
  );
}
