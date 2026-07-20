import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import type { Repo, ReviewTask } from "../types";
import { repoApi } from "../api/repos";
import { reviewApi } from "../api/reviews";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
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

      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold tracking-tight">{repo.name}</h1>
        <Button onClick={() => setReviewModalOpen(true)}>发起审查</Button>
      </div>

      <p className="text-sm text-muted-foreground">
        {repo.git_url} · 本地: {repo.local_path}
        {confirmDelete ? (
          <span className="ml-4">
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
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="text-sm font-medium block mb-1">类型</label>
              <div className="flex rounded-md border h-9">
                <button
                  className={`px-3 text-sm ${reviewType === "local" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                  onClick={() => setReviewType("local")}
                >
                  Local Commit
                </button>
                <button
                  className={`px-3 text-sm rounded-r-md ${reviewType === "pr" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                  onClick={() => setReviewType("pr")}
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
                  className="flex h-9 w-44 rounded-md border bg-background px-3 py-1 text-sm font-mono"
                  value={commitHash}
                  onChange={(e) => setCommitHash(e.target.value)}
                  placeholder="留空使用 HEAD"
                />
              </div>
            )}
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting ? "提交中..." : "提交审查"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Review history */}
      <Card>
        <CardHeader><CardTitle className="text-base">审查历史</CardTitle></CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left font-medium text-muted-foreground px-6 py-3">类型</th>
                <th className="text-left font-medium text-muted-foreground px-6 py-3">标识</th>
                <th className="text-left font-medium text-muted-foreground px-6 py-3">状态</th>
                <th className="text-left font-medium text-muted-foreground px-6 py-3">时间</th>
                <th className="text-right font-medium text-muted-foreground px-6 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">暂无审查记录</td>
                </tr>
              ) : (
                tasks.map((t) => (
                  <tr key={t.id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="px-6 py-3">{t.review_type === "pr" ? "PR" : "Local"}</td>
                    <td className="px-6 py-3 text-muted-foreground">
                      {t.pr_number ? `#${t.pr_number}` : t.commit_hash?.slice(0, 7) || "—"}
                    </td>
                    <td className="px-6 py-3">
                      <Badge variant={statusVariant[t.status] || "secondary"}>
                        {statusLabel[t.status] || t.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-muted-foreground">
                      {new Date(t.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-3 text-right">
                      {t.status === "done" && (
                        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => navigate(`/reviews/${t.id}`)}>
                          查看报告
                        </Button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
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
