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

function getErrorMessage(error: unknown, fallback: string) {
  const responseError = error as {
    response?: { data?: { detail?: string } };
    message?: string;
  };
  return responseError.response?.data?.detail || responseError.message || fallback;
}

export default function RepoList() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [editing, setEditing] = useState<Repo | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [gitUrl, setGitUrl] = useState("");
  const [saving, setSaving] = useState(false);

  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await repoApi.list();
      setRepos(res.data);
    } catch (loadError) {
      setError(getErrorMessage(loadError, "无法加载仓库列表"));
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
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (repo: Repo) => {
    setEditing(repo);
    setName(repo.name);
    setGitUrl(repo.git_url);
    setFormError(null);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!name.trim() || !gitUrl.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      if (editing) {
        await repoApi.update(editing.id, { name: name.trim(), git_url: gitUrl.trim() });
      } else {
        await repoApi.create({ name: name.trim(), git_url: gitUrl.trim() });
      }
      setShowForm(false);
      await load();
    } catch (saveError) {
      setFormError(getErrorMessage(saveError, "保存仓库失败"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await repoApi.remove(id);
      setConfirmDelete(null);
      await load();
    } catch (deleteError) {
      setError(getErrorMessage(deleteError, "删除仓库失败"));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold tracking-tight">仓库管理</h1>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button className="w-full sm:w-auto" onClick={() => setReviewModalOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            发起审查
          </Button>
          <Button className="w-full sm:w-auto" variant="outline" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" />
            添加仓库
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {error && (
            <div className="flex items-center justify-between gap-4 border-b border-destructive/30 bg-destructive/5 px-6 py-3 text-sm">
              <span className="text-destructive">{error}</span>
              <Button variant="outline" size="sm" onClick={() => void load()}>重试</Button>
            </div>
          )}
          <Table className="min-w-[680px]">
            <TableHeader>
              <TableRow>
                <TableHead className="px-6 py-3 text-muted-foreground">名称</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">Git URL</TableHead>
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
                    <TableCell className="px-6 py-3 max-w-[320px] truncate text-muted-foreground" title={repo.git_url}>
                      {repo.git_url}
                    </TableCell>
                    <TableCell className="px-6 py-3 text-right">
                      <div className="flex items-center justify-end gap-3">
                        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => navigate(`/repos/${repo.id}`)}>详情</Button>
                        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => openEdit(repo)}>编辑</Button>
                        {confirmDelete === repo.id ? (
                          <span className="text-sm">
                            确定？{" "}
                            <Button variant="link" size="sm" className="h-auto p-0 text-destructive" onClick={() => void handleDelete(repo.id)}>删除</Button>
                            {" "}/{" "}
                            <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setConfirmDelete(null)}>取消</Button>
                          </span>
                        ) : (
                          <Button variant="link" size="sm" className="h-auto p-0 text-destructive" onClick={() => setConfirmDelete(repo.id)}>删除</Button>
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

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowForm(false)}>
          <div
            className="bg-card border rounded-lg shadow-lg w-full max-w-md p-6 space-y-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="repo-form-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-4">
              <h2 id="repo-form-title" className="text-lg font-semibold">{editing ? "编辑仓库" : "添加仓库"}</h2>
              <Button variant="ghost" size="icon" aria-label="关闭仓库表单" onClick={() => setShowForm(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="space-y-3">
              <div>
                <label htmlFor="repo-name" className="text-sm font-medium">名称</label>
                <input id="repo-name" className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={name} onChange={(event) => setName(event.target.value)} placeholder="仓库名称" />
              </div>
              <div>
                <label htmlFor="repo-git-url" className="text-sm font-medium">Git URL</label>
                <input id="repo-git-url" className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={gitUrl} onChange={(event) => setGitUrl(event.target.value)} placeholder="https://github.com/... 或 https://gitee.com/..." />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">添加后会同步仓库分支，发起审查时再选择目标分支。</p>
            {formError && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{formError}</div>}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowForm(false)}>取消</Button>
              <Button onClick={() => void handleSave()} disabled={saving || !name.trim() || !gitUrl.trim()}>
                {saving ? "保存中..." : "保存"}
              </Button>
            </div>
          </div>
        </div>
      )}

      <SubmitReviewModal open={reviewModalOpen} onClose={() => setReviewModalOpen(false)} />
    </div>
  );
}
