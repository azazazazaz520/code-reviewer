import { ExternalLink, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { getDesktopBridge } from "../../runtime/desktop";
import type { DesktopRuntimeInfo, SidecarState } from "../../runtime/desktop";
import type { EffectiveSettingsSnapshot } from "../../types/settings";
import { toUserError } from "../../utils/error-message";
import { Button } from "../ui/button";
import SectionCard from "./SectionCard";
import RuntimeStatusCard from "./RuntimeStatusCard";
import { settingInputClassName, SettingsForm, type SaveSettings } from "./SettingsForm";

interface StorageSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
  runtime: DesktopRuntimeInfo | null;
  sidecarState: SidecarState | null;
  onSaved: SaveSettings;
}

export default function StorageSettings({ snapshot, runtime, sidecarState, onSaved }: StorageSettingsProps) {
  const [reposDir, setReposDir] = useState(snapshot.settings.storage.repos_dir);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const bridge = getDesktopBridge();

  useEffect(() => setReposDir(snapshot.settings.storage.repos_dir), [snapshot.settings.storage.repos_dir]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await onSaved({ storage: { repos_dir: reposDir.trim() } });
      setMessage("数据目录设置已保存");
    } catch (saveError) {
      setError(toUserError(saveError, "数据目录设置保存失败，请检查路径后重试。").message);
    } finally {
      setSaving(false);
    }
  };

  const chooseDirectory = async () => {
    if (!bridge) return;
    const selected = await bridge.chooseDirectory();
    if (selected) setReposDir(selected);
  };

  const openDataDirectory = async () => {
    if (!runtime || !bridge) return;
    setOpenError(null);
    const result = await bridge.openPath(runtime.dataDir);
    if (!result.ok) setOpenError(result.error || "无法打开数据目录");
  };

  return (
    <div className="space-y-4">
      <SectionCard title="数据目录" description="管理新建仓库使用的目录，并查看应用运行数据。">
        <SettingsForm onSubmit={save} saving={saving} message={message} error={error}>
          <div className="flex items-end gap-2 border-b border-border/70 py-4">
            <div className="min-w-0 flex-1">
              <label className="block">
                <span className="block text-sm font-medium">仓库根目录</span>
                <span className="mt-1 block text-xs leading-5 text-muted-foreground">修改后，新建或重新同步的仓库使用该目录。</span>
                <input className={`${settingInputClassName} mt-2`} value={reposDir} onChange={(event) => setReposDir(event.target.value)} />
              </label>
            </div>
            {bridge && <Button type="button" variant="outline" className="mb-4 min-h-11" onClick={() => void chooseDirectory()}><FolderOpen className="h-4 w-4" aria-hidden="true" />选择目录</Button>}
          </div>
        </SettingsForm>
        <div className="border-t border-border/70 pt-4">
          <div className="text-sm font-medium">应用数据目录</div>
          <p className="mt-1 break-all font-mono text-xs leading-5 text-foreground">{runtime?.dataDir || "浏览器模式不可读取本地数据目录"}</p>
          {runtime && bridge ? (
            <Button type="button" variant="outline" className="mt-3 min-h-11" onClick={() => void openDataDirectory()}>
              <FolderOpen className="h-4 w-4" aria-hidden="true" />
              打开数据目录
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">浏览器模式不具备打开本地路径的桌面能力。</p>
          )}
          {openError && <p className="mt-2 text-xs text-destructive" role="alert">{openError}</p>}
        </div>
      </SectionCard>
      <RuntimeStatusCard runtime={runtime} sidecarState={sidecarState} />
    </div>
  );
}
