import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, X } from "lucide-react";
import type { CommitItem, PRItem, Repo } from "../types";
import { repoApi } from "../api/repos";
import { reviewApi } from "../api/reviews";
import { Button } from "./ui/button";

interface Props {
  open: boolean;
  onClose: () => void;
  preSelectedRepoId?: string;
}

function getErrorMessage(error: unknown, fallback: string) {
  const responseError = error as {
    response?: { data?: { detail?: string } };
    message?: string;
  };
  return responseError.response?.data?.detail || responseError.message || fallback;
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

function getPullRequestLabel(gitUrl?: string) {
  return gitUrl?.toLowerCase().includes("gitee.com") ? "Gitee PR" : "GitHub PR";
}

export default function SubmitReviewModal({ open, onClose, preSelectedRepoId }: Props) {
  const navigate = useNavigate();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [repoId, setRepoId] = useState<string | null>(preSelectedRepoId ?? null);
  const [reviewType, setReviewType] = useState<"pr" | "local">("pr");
  const [branches, setBranches] = useState<string[]>([]);
  const [branch, setBranch] = useState("");
  const [prs, setPRs] = useState<PRItem[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [loadingTargets, setLoadingTargets] = useState(false);
  const [loadingCommits, setLoadingCommits] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [reposError, setReposError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [branchError, setBranchError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [selectedPR, setSelectedPR] = useState<number | null>(null);
  const [selectedCommit, setSelectedCommit] = useState<string | null>(null);
  const [manualPR, setManualPR] = useState("");
  const [manualCommit, setManualCommit] = useState("");
  const selectedRepo = repos.find((repo) => repo.id === repoId);

  useEffect(() => {
    if (!open) return;
    setRepoId(preSelectedRepoId ?? null);
    setReviewType("pr");
    setBranches([]);
    setBranch("");
    setPRs([]);
    setCommits([]);
    setSelectedPR(null);
    setSelectedCommit(null);
    setManualPR("");
    setManualCommit("");
    setReposError(null);
    setListError(null);
    setBranchError(null);
    setSubmitError(null);
    setLoadingRepos(true);
    repoApi.list()
      .then((res) => setRepos(res.data))
      .catch((error) => setReposError(getErrorMessage(error, "无法加载仓库列表")))
      .finally(() => setLoadingRepos(false));
  }, [open, preSelectedRepoId]);

  useEffect(() => {
    if (!repoId) {
      setPRs([]);
      setBranches([]);
      setCommits([]);
      setListError(null);
      setBranchError(null);
      return;
    }

    setSelectedPR(null);
    setSelectedCommit(null);
    setListError(null);
    setBranchError(null);
    setSubmitError(null);
    setLoadingTargets(true);

    if (reviewType === "pr") {
      setBranches([]);
      setBranch("");
      reviewApi.listPRs(repoId)
        .then((res) => setPRs(res.data))
        .catch((error) => setListError(getErrorMessage(error, "无法加载 PR 列表")))
        .finally(() => setLoadingTargets(false));
      return;
    }

    setPRs([]);
    setBranch("");
    setCommits([]);
    repoApi.branches(repoId)
      .then((res) => setBranches(res.data.map((item) => item.name)))
      .catch((error) => setBranchError(getErrorMessage(error, "无法加载分支列表")))
      .finally(() => setLoadingTargets(false));
  }, [repoId, reviewType]);

  useEffect(() => {
    if (!repoId || reviewType !== "local" || !branch) {
      setCommits([]);
      setLoadingCommits(false);
      return;
    }

    setLoadingCommits(true);
    setListError(null);
    setSelectedCommit(null);
    reviewApi.listCommits(repoId, branch)
      .then((res) => setCommits(res.data))
      .catch((error) => setListError(getErrorMessage(error, "无法加载该分支的 Commit 列表")))
      .finally(() => setLoadingCommits(false));
  }, [repoId, reviewType, branch]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  const handleSubmit = async () => {
    if (!repoId) return;
    const prNumber = selectedPR || (manualPR ? parseInt(manualPR, 10) : undefined);
    const commitHash = selectedCommit || manualCommit.trim() || undefined;
    if (reviewType === "pr" && !prNumber) {
      setSubmitError("请选择 PR 或输入 PR 编号");
      return;
    }
    if (reviewType === "local" && !branch) {
      setSubmitError("请选择审查分支");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await reviewApi.submit(repoId, {
        review_type: reviewType,
        pr_number: reviewType === "pr" ? prNumber : undefined,
        commit_hash: reviewType === "local" ? commitHash : undefined,
        branch: reviewType === "local" ? branch : undefined,
      });
      onClose();
      navigate(`/reviews/${response.data.id}`);
    } catch (error) {
      setSubmitError(getErrorMessage(error, "提交审查失败"));
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        className="bg-card border rounded-lg shadow-lg w-full max-w-xl max-h-[90vh] overflow-auto p-6 space-y-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="submit-review-title"
      >
        <div className="flex items-center justify-between gap-4">
          <h2 id="submit-review-title" className="text-lg font-semibold">发起审查</h2>
          <Button variant="ghost" size="icon" aria-label="关闭发起审查弹窗" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div>
          <label htmlFor="submit-review-repo" className="text-sm font-medium block mb-1">仓库</label>
          <select id="submit-review-repo" className="flex h-10 w-full rounded-md border bg-background px-3 py-1 text-sm" value={repoId || ""} onChange={(event) => setRepoId(event.target.value || null)} disabled={loadingRepos || repos.length === 0}>
            <option value="">{loadingRepos ? "加载仓库中..." : "选择仓库"}</option>
            {repos.map((repo) => <option key={repo.id} value={repo.id}>{repo.name}</option>)}
          </select>
          {reposError && <div role="alert" className="mt-2 text-sm text-destructive">{reposError}</div>}
        </div>

        <div>
          <span className="text-sm font-medium block mb-1">审查类型</span>
          <div className="flex rounded-md border h-10 w-fit" role="group" aria-label="审查类型">
            <button type="button" className={`px-4 text-sm rounded-l-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${reviewType === "pr" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setReviewType("pr")} aria-pressed={reviewType === "pr"}>{getPullRequestLabel(selectedRepo?.git_url)} 审查</button>
            <button type="button" className={`px-4 text-sm rounded-r-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${reviewType === "local" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setReviewType("local")} aria-pressed={reviewType === "local"}>Local Commit</button>
          </div>
        </div>

        {reviewType === "local" && (
          <div>
            <label htmlFor="submit-review-branch" className="text-sm font-medium block mb-1">审查分支</label>
            {branches.length > 0 ? (
              <select id="submit-review-branch" className="flex h-10 w-full rounded-md border bg-background px-3 py-1 text-sm" value={branch} onChange={(event) => setBranch(event.target.value)} disabled={loadingTargets}>
                <option value="">{loadingTargets ? "加载分支中..." : "选择分支"}</option>
                {branches.map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            ) : (
              <input id="submit-review-branch" className="flex h-10 w-full rounded-md border bg-background px-3 py-1 text-sm font-mono" value={branch} onChange={(event) => setBranch(event.target.value)} placeholder={loadingTargets ? "加载分支中..." : "输入分支名称"} disabled={loadingTargets} />
            )}
            {branchError && <div role="alert" className="mt-2 text-sm text-destructive">{branchError}</div>}
            <p className="mt-1 text-xs text-muted-foreground">选择分支后可继续选择该分支上的具体 Commit；留空则审查分支最新提交。</p>
          </div>
        )}

        <div>
          <span className="text-sm font-medium block mb-1">{reviewType === "pr" ? "选择 PR" : "选择 Commit（可选）"}</span>
          {reviewType === "local" && !branch && <div className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">请先选择审查分支</div>}
          {(loadingTargets || loadingCommits) && (
            <div className="flex items-center gap-2 py-4 text-muted-foreground text-sm"><Loader2 className="h-4 w-4 animate-spin" />加载中...</div>
          )}

          {listError && (
            <div className="space-y-2 mb-2">
              <div role="alert" className="text-sm text-destructive bg-destructive/5 border border-destructive/30 rounded-md p-3">{listError}</div>
              {reviewType === "pr" ? (
                <div>
                  <label htmlFor="manual-pr-number" className="text-sm">手动输入 PR 编号</label>
                  <input id="manual-pr-number" type="number" min={1} className="mt-1 flex h-10 w-32 rounded-md border bg-background px-3 py-1 text-sm" value={manualPR} onChange={(event) => setManualPR(event.target.value)} />
                </div>
              ) : (
                <div>
                  <label htmlFor="manual-commit-hash" className="text-sm">手动输入 Commit Hash</label>
                  <input id="manual-commit-hash" className="mt-1 flex h-10 w-full rounded-md border bg-background px-3 py-1 text-sm font-mono" value={manualCommit} onChange={(event) => setManualCommit(event.target.value)} placeholder="留空审查分支最新提交" />
                </div>
              )}
            </div>
          )}

          {!loadingTargets && !loadingCommits && !listError && (reviewType === "pr" || branch) && (
            <div className="border rounded-md max-h-60 overflow-auto" role="listbox" aria-label={reviewType === "pr" ? "PR 列表" : "Commit 列表"}>
              {reviewType === "pr" ? (
                prs.length === 0 ? (
                  <div className="p-4 text-center text-sm text-muted-foreground">该仓库暂无 Open PR，也可以手动输入 PR 编号</div>
                ) : prs.map((pr) => (
                  <button key={pr.number} type="button" role="option" aria-selected={selectedPR === pr.number} className={`block w-full border-b last:border-0 px-3 py-3 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selectedPR === pr.number ? "bg-primary/10 border-l-2 border-l-primary" : ""}`} onClick={() => setSelectedPR(selectedPR === pr.number ? null : pr.number)}>
                    <div className="font-medium">#{pr.number} — {pr.title}</div>
                    <div className="text-xs text-muted-foreground">{pr.author} · {pr.branch} · {timeAgo(pr.created_at)}</div>
                  </button>
                ))
              ) : commits.length === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">该分支暂无 Commit 记录，也可以手动输入 Hash</div>
              ) : commits.map((commit) => (
                <button key={commit.hash} type="button" role="option" aria-selected={selectedCommit === commit.hash} className={`block w-full border-b last:border-0 px-3 py-3 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selectedCommit === commit.hash ? "bg-primary/10 border-l-2 border-l-primary" : ""}`} onClick={() => setSelectedCommit(selectedCommit === commit.hash ? null : commit.hash)}>
                  <div className="font-medium font-mono">{commit.short_hash}</div>
                  <div className="text-xs text-muted-foreground">{commit.message} · {commit.author} · {timeAgo(commit.date)}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {submitError && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{submitError}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting || !repoId || (reviewType === "local" && !branch)}>
            {submitting ? "提交中..." : "开始审查"}
          </Button>
        </div>
      </div>
    </div>
  );
}
