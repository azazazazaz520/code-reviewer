import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import type { PRItem, CommitItem, Repo } from "../types";
import { repoApi } from "../api/repos";
import { reviewApi } from "../api/reviews";
import { Button } from "./ui/button";

interface Props {
  open: boolean;
  onClose: () => void;
  preSelectedRepoId?: string;
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "刚刚";
  if (hours < 24) return `${hours}h 前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d 前`;
  return new Date(iso).toLocaleDateString();
}

export default function SubmitReviewModal({ open, onClose, preSelectedRepoId }: Props) {
  const navigate = useNavigate();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [repoId, setRepoId] = useState<string | null>(preSelectedRepoId ?? null);
  const [reviewType, setReviewType] = useState<"pr" | "local">("pr");
  const [prs, setPRs] = useState<PRItem[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedPR, setSelectedPR] = useState<number | null>(null);
  const [selectedCommit, setSelectedCommit] = useState<string | null>(null);
  const [manualPR, setManualPR] = useState("");
  const [manualCommit, setManualCommit] = useState("");

  useEffect(() => {
    if (open) repoApi.list().then((res) => setRepos(res.data)).catch(() => {});
  }, [open]);

  useEffect(() => {
    if (preSelectedRepoId) setRepoId(preSelectedRepoId);
  }, [preSelectedRepoId]);

  useEffect(() => {
    if (!repoId) { setPRs([]); setCommits([]); setListError(null); return; }
    setLoadingList(true);
    setListError(null);
    setSelectedPR(null);
    setSelectedCommit(null);
    const fetcher = reviewType === "pr"
      ? reviewApi.listPRs(repoId).then((res) => setPRs(res.data))
      : reviewApi.listCommits(repoId).then((res) => setCommits(res.data));
    fetcher.catch((err: any) => {
      setListError(err?.response?.data?.detail || "无法加载列表");
    }).finally(() => setLoadingList(false));
  }, [repoId, reviewType]);

  const handleSubmit = async () => {
    if (!repoId) return;
    const prNumber = selectedPR || (manualPR ? parseInt(manualPR) : undefined);
    const commitHash = selectedCommit || manualCommit || undefined;
    if (reviewType === "pr" && !prNumber) return;
    setSubmitting(true);
    try {
      const res = await reviewApi.submit(repoId, {
        review_type: reviewType,
        pr_number: prNumber ?? undefined,
        commit_hash: commitHash || undefined,
      });
      reset();
      onClose();
      navigate(`/reviews/${res.data.id}`);
    } catch { /* ignore */ }
    finally { setSubmitting(false); }
  };

  const reset = () => {
    setSelectedPR(null);
    setSelectedCommit(null);
    setManualPR("");
    setManualCommit("");
    setListError(null);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => { reset(); onClose(); }}>
      <div className="bg-card border rounded-lg shadow-lg w-full max-w-xl max-h-[90vh] overflow-auto p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">发起审查</h2>

        {/* Repo select */}
        <div>
          <label className="text-sm font-medium block mb-1">仓库</label>
          <select
            className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
            value={repoId || ""}
            onChange={(e) => setRepoId(e.target.value || null)}
          >
            <option value="">选择仓库</option>
            {repos.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>

        {/* Type toggle */}
        <div>
          <label className="text-sm font-medium block mb-1">审查类型</label>
          <div className="flex rounded-md border h-9 w-fit">
            <button className={`px-4 text-sm ${reviewType === "pr" ? "bg-primary text-primary-foreground" : ""}`} onClick={() => setReviewType("pr")}>PR 审查</button>
            <button className={`px-4 text-sm rounded-r-md ${reviewType === "local" ? "bg-primary text-primary-foreground" : ""}`} onClick={() => setReviewType("local")}>Local Commit</button>
          </div>
        </div>

        {/* Target list */}
        <div>
          <label className="text-sm font-medium block mb-1">
            {reviewType === "pr" ? "选择 PR" : "选择 Commit"}
          </label>

          {loadingList && (
            <div className="flex items-center gap-2 py-4 text-muted-foreground text-sm">
              <Loader2 className="h-4 w-4 animate-spin" />加载中...
            </div>
          )}

          {listError && (
            <div className="space-y-2 mb-2">
              <div className="text-sm text-yellow-600 bg-yellow-50 border border-yellow-200 rounded-md p-3 dark:bg-yellow-950 dark:border-yellow-800 dark:text-yellow-400">
                {listError}
              </div>
              {reviewType === "pr" ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm">手动输入 PR 编号：</span>
                  <input type="number" min={1} className="flex h-9 w-32 rounded-md border bg-background px-3 py-1 text-sm" value={manualPR} onChange={(e) => setManualPR(e.target.value)} />
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-sm">手动输入 Commit Hash：</span>
                  <input className="flex h-9 w-44 rounded-md border bg-background px-3 py-1 text-sm font-mono" value={manualCommit} onChange={(e) => setManualCommit(e.target.value)} placeholder="留空使用 HEAD" />
                </div>
              )}
            </div>
          )}

          {!loadingList && !listError && (
            <div className="border rounded-md max-h-60 overflow-auto">
              {reviewType === "pr" ? (
                prs.length === 0 ? (
                  <div className="p-4 text-center text-sm text-muted-foreground">该仓库暂无 Open PR</div>
                ) : (
                  prs.map((pr) => (
                    <div
                      key={pr.number}
                      className={`px-3 py-2 cursor-pointer border-b last:border-0 hover:bg-muted text-sm ${selectedPR === pr.number ? "bg-primary/10 border-l-2 border-l-primary" : ""}`}
                      onClick={() => setSelectedPR(selectedPR === pr.number ? null : pr.number)}
                    >
                      <div className="font-medium">#{pr.number} — {pr.title}</div>
                      <div className="text-xs text-muted-foreground">{pr.author} · {timeAgo(pr.created_at)}</div>
                    </div>
                  ))
                )
              ) : (
                commits.length === 0 ? (
                  <div className="p-4 text-center text-sm text-muted-foreground">该仓库无 Commit 记录</div>
                ) : (
                  commits.map((c) => (
                    <div
                      key={c.hash}
                      className={`px-3 py-2 cursor-pointer border-b last:border-0 hover:bg-muted text-sm ${selectedCommit === c.hash ? "bg-primary/10 border-l-2 border-l-primary" : ""}`}
                      onClick={() => setSelectedCommit(selectedCommit === c.hash ? null : c.hash)}
                    >
                      <div className="font-medium font-mono">{c.short_hash}</div>
                      <div className="text-xs text-muted-foreground">{c.message} · {c.author} · {timeAgo(c.date)}</div>
                    </div>
                  ))
                )
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => { reset(); onClose(); }}>取消</Button>
          <Button onClick={handleSubmit} disabled={submitting || !repoId}>
            {submitting ? "提交中..." : "开始审查"}
          </Button>
        </div>
      </div>
    </div>
  );
}
