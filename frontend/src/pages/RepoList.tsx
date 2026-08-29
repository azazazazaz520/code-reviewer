import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { Repo } from "../types";
import { repoApi } from "../api/repos";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import SubmitReviewModal from "../components/SubmitReviewModal";
import ErrorNotice from "../components/ErrorNotice";
import { toUserError, type UserErrorInfo } from "../utils/error-message";
import { Modal } from "../components/ui/modal";

export default function RepoList() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [editing, setEditing] = useState<Repo | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UserErrorInfo | null>(null);
  const [formError, setFormError] = useState<UserErrorInfo | null>(null);

  const [name, setName] = useState("");
  const [gitUrl, setGitUrl] = useState("");
  const [repoKind, setRepoKind] = useState<"remote" | "workspace">("remote");
  const [localPath, setLocalPath] = useState("");
  const [saving, setSaving] = useState(false);

  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await repoApi.list();
      setRepos(res.data);
    } catch (loadError) {
      setError(toUserError(loadError, "无法加载仓库列表"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const openAdd = () => {
    setEditing(null);
    setName("");
    setGitUrl("");
    setRepoKind("remote");
    setLocalPath("");
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (repo: Repo) => {
    setEditing(repo);
    setName(repo.name);
    setGitUrl(repo.git_url);
    setRepoKind(repo.git_url ? "remote" : "workspace");
    setLocalPath(repo.local_path || "");
    setFormError(null);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    if (repoKind === "remote" && !gitUrl.trim()) return;
    if (repoKind === "workspace" && !localPath.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      if (repoKind === "workspace") {
        if (editing) {
          await repoApi.updateWorkspace(editing.id, {
            name: name.trim(),
            path: localPath.trim(),
          });
        } else {
          await repoApi.createWorkspace({
            name: name.trim(),
            path: localPath.trim(),
          });
        }
      } else if (editing) {
        await repoApi.update(editing.id, { name: name.trim(), git_url: gitUrl.trim() });
      } else {
        await repoApi.create({ name: name.trim(), git_url: gitUrl.trim() });
      }
      setShowForm(false);
      await load();
    } catch (saveError) {
      setFormError(toUserError(saveError, "保存仓库失败"));
    } finally {
      setSaving(false);
    }
  };

  const chooseLocalPath = async () => {
    if (!window.desktop) {
      setFormError(toUserError(null, "添加本地仓库需要使用桌面应用"));
      return;
    }
    const selected = await window.desktop.chooseDirectory();
    if (selected) {
      setLocalPath(selected);
      setFormError(null);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await repoApi.remove(id);
      setConfirmDelete(null);
      await load();
    } catch (deleteError) {
      setError(toUserError(deleteError, "删除仓库失败"));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">仓库管理</h1>
        <div className="flex flex-col gap-2 sm:flex-row">
            <Button className="min-h-11 w-full sm:w-auto" onClick={() => setReviewModalOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            发起审查
          </Button>
          <Button className="min-h-11 w-full sm:w-auto" variant="outline" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" />
            添加仓库
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {error && (
            <div className="flex items-center justify-between gap-4 border-b border-destructive/30 bg-destructive/5 px-6 py-3 text-sm">
              <ErrorNotice error={error} onRetry={() => void load()} compact className="w-full" />
            </div>
          )}
          <Table className="min-w-[680px]">
            <TableHeader>
              <TableRow>
                <TableHead className="px-6 py-3 text-muted-foreground">名称</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">来源</TableHead>
                <TableHead className="px-6 py-3 text-right text-muted-foreground w-48">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={3} className="px-6 py-10 text-center text-muted-foreground">加载中...</TableCell>
                </TableRow>
              ) : repos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="px-6 py-12 text-center text-muted-foreground">
                    暂无仓库，点击「添加仓库」开始
                  </TableCell>
                </TableRow>
              ) : (
                repos.map((repo) => (
                  <TableRow key={repo.id}>
                    <TableCell className="px-6 py-3 font-medium">{repo.name}</TableCell>
                    <TableCell className="px-6 py-3 max-w-[320px] truncate text-muted-foreground" title={repo.git_url || repo.local_path}>
                      {repo.git_url || repo.local_path || "本地工作区"}
                    </TableCell>
                    <TableCell className="px-6 py-3 text-right">
                      <div className="flex items-center justify-end gap-3">
                        <Button variant="link" size="sm" className="min-h-11 px-2 sm:min-h-0 sm:h-auto sm:p-0" onClick={() => navigate(`/repos/${repo.id}`)}>详情</Button>
                        <Button variant="link" size="sm" className="min-h-11 px-2 sm:min-h-0 sm:h-auto sm:p-0" onClick={() => openEdit(repo)}>编辑</Button>
                        {confirmDelete === repo.id ? (
                          <span className="text-sm">
                            确定？{" "}
                            <Button variant="link" size="sm" className="min-h-11 px-2 text-destructive sm:min-h-0 sm:h-auto sm:p-0" onClick={() => void handleDelete(repo.id)}>删除</Button>
                            {" "}/{" "}
                            <Button variant="link" size="sm" className="min-h-11 px-2 sm:min-h-0 sm:h-auto sm:p-0" onClick={() => setConfirmDelete(null)}>取消</Button>
                          </span>
                        ) : (
                          <Button variant="link" size="sm" className="min-h-11 px-2 text-destructive sm:min-h-0 sm:h-auto sm:p-0" onClick={() => setConfirmDelete(repo.id)}>删除</Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Modal open={showForm} onClose={() => setShowForm(false)} titleId="repo-form-title" panelClassName="max-w-md space-y-4">
            <div className="flex items-center justify-between gap-4">
              <h2 id="repo-form-title" className="text-lg font-semibold">{editing ? "编辑仓库" : "添加仓库"}</h2>
              <Button variant="ghost" size="icon" className="min-h-11 min-w-11" aria-label="关闭仓库表单" onClick={() => setShowForm(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="space-y-3">
              <div>
                <span className="text-sm font-medium">仓库来源</span>
                <div className="mt-1 flex rounded-md border h-9 w-fit" role="group" aria-label="仓库来源">
                  <button type="button" className={`px-3 text-sm rounded-l-md ${repoKind === "remote" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setRepoKind("remote")} aria-pressed={repoKind === "remote"}>远程仓库</button>
                  <button type="button" className={`px-3 text-sm rounded-r-md ${repoKind === "workspace" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setRepoKind("workspace")} aria-pressed={repoKind === "workspace"}>本地仓库</button>
                </div>
              </div>
              <div>
                <label htmlFor="repo-name" className="text-sm font-medium">名称</label>
                <input id="repo-name" className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={name} onChange={(event) => setName(event.target.value)} placeholder="仓库名称" />
              </div>
              {repoKind === "remote" ? <div>
                <label htmlFor="repo-git-url" className="text-sm font-medium">Git URL</label>
                <input id="repo-git-url" className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={gitUrl} onChange={(event) => setGitUrl(event.target.value)} placeholder="https://github.com/... 或 https://gitee.com/..." />
              </div> : <div>
                <label className="text-sm font-medium">本地工作区</label>
                <div className="mt-1 flex gap-2">
                  <Button type="button" variant="outline" className="min-h-11" onClick={() => void chooseLocalPath()}>选择目录</Button>
                  <div className="min-w-0 flex-1 rounded-md border bg-muted/30 px-3 py-2 text-sm font-mono truncate">
                    {localPath || "尚未选择本地工作区"}
                  </div>
                </div>
              </div>}
            </div>
            <p className="text-xs text-muted-foreground">{repoKind === "remote" ? "添加后会同步远程分支，发起审查时选择目标提交。" : "添加后可在发起审查时选择指定提交或未提交改动。"}</p>
            {formError && <ErrorNotice error={formError} compact />}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" className="min-h-11" onClick={() => setShowForm(false)}>取消</Button>
              <Button className="min-h-11" onClick={() => void handleSave()} disabled={saving || !name.trim() || (repoKind === "remote" ? !gitUrl.trim() : !localPath.trim())}>
                {saving ? "保存中..." : "保存"}
              </Button>
            </div>
      </Modal>

      <SubmitReviewModal open={reviewModalOpen} onClose={() => setReviewModalOpen(false)} />
    </div>
  );
}
