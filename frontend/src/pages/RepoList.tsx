import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
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

export default function RepoList() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [editing, setEditing] = useState<Repo | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  /* form state */
  const [name, setName] = useState("");
  const [gitUrl, setGitUrl] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [defaultBranch, setDefaultBranch] = useState("main");
  const [saving, setSaving] = useState(false);

  const navigate = useNavigate();

  const load = () => repoApi.list().then((res) => setRepos(res.data));

  useEffect(() => { load(); }, []);

  const openAdd = () => {
    setEditing(null);
    setName("");
    setGitUrl("");
    setLocalPath("");
    setDefaultBranch("main");
    setShowForm(true);
  };

  const openEdit = (repo: Repo) => {
    setEditing(repo);
    setName(repo.name);
    setGitUrl(repo.git_url);
    setLocalPath(repo.local_path);
    setDefaultBranch(repo.default_branch);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!name || !gitUrl || !localPath) return;
    setSaving(true);
    try {
      if (editing) {
        await repoApi.update(editing.id, { name, git_url: gitUrl, local_path: localPath, default_branch: defaultBranch });
      } else {
        await repoApi.create({ name, git_url: gitUrl, local_path: localPath, default_branch: defaultBranch });
      }
      setShowForm(false);
      load();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    await repoApi.remove(id);
    setConfirmDelete(null);
    load();
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
          <Table className="min-w-[820px]">
            <TableHeader>
              <TableRow>
                <TableHead className="px-6 py-3 text-muted-foreground">名称</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">Git URL</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">本地路径</TableHead>
                <TableHead className="px-6 py-3 text-muted-foreground">默认分支</TableHead>
                <TableHead className="px-6 py-3 text-right text-muted-foreground w-48">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {repos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    暂无仓库，点击「添加仓库」开始
                  </TableCell>
                </TableRow>
              ) : (
                repos.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="px-6 py-3 font-medium">{r.name}</TableCell>
                    <TableCell className="px-6 py-3 max-w-[240px] truncate text-muted-foreground" title={r.git_url}>
                      {r.git_url}
                    </TableCell>
                    <TableCell className="px-6 py-3 max-w-[240px] truncate text-muted-foreground" title={r.local_path}>
                      {r.local_path}
                    </TableCell>
                    <TableCell className="px-6 py-3 text-muted-foreground">{r.default_branch}</TableCell>
                    <TableCell className="px-6 py-3 text-right">
                      <div className="flex items-center justify-end gap-3">
                        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => navigate(`/repos/${r.id}`)}>详情</Button>
                        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => openEdit(r)}>编辑</Button>
                        {confirmDelete === r.id ? (
                          <span className="text-sm">
                            确定？{" "}
                            <Button variant="link" size="sm" className="h-auto p-0 text-destructive" onClick={() => handleDelete(r.id)}>删除</Button>
                            {" "}/{" "}
                            <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setConfirmDelete(null)}>取消</Button>
                          </span>
                        ) : (
                          <Button variant="link" size="sm" className="h-auto p-0 text-destructive" onClick={() => setConfirmDelete(r.id)}>删除</Button>
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

      {/* Add/Edit overlay */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowForm(false)}>
          <div className="bg-card border rounded-lg shadow-lg w-[calc(100vw-2rem)] max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold">{editing ? "编辑仓库" : "添加仓库"}</h2>
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium">名称</label>
                <input className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="仓库名称" />
              </div>
              <div>
                <label className="text-sm font-medium">Git URL</label>
                <input className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} placeholder="https://github.com/..." />
              </div>
              <div>
                <label className="text-sm font-medium">本地路径</label>
                <input className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={localPath} onChange={(e) => setLocalPath(e.target.value)} placeholder="/path/to/repo" />
              </div>
              <div>
                <label className="text-sm font-medium">默认分支</label>
                <input className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={defaultBranch} onChange={(e) => setDefaultBranch(e.target.value)} />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowForm(false)}>取消</Button>
              <Button onClick={handleSave} disabled={saving || !name || !gitUrl || !localPath}>
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
