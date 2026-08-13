import { ExternalLink, FolderOpen } from "lucide-react";
import { useState } from "react";
import { getDesktopBridge } from "../../runtime/desktop";
import type { EffectiveSettingsSnapshot } from "../../types/settings";
import { Button } from "../ui/button";
import SectionCard from "./SectionCard";
import RuntimeStatusCard from "./RuntimeStatusCard";

interface StorageSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
  runtime: import("../../runtime/desktop").DesktopRuntimeInfo | null;
  sidecarState: import("../../runtime/desktop").SidecarState | null;
}

export default function StorageSettings({ snapshot, runtime, sidecarState }: StorageSettingsProps) {
  const [openError, setOpenError] = useState<string | null>(null);
  const bridge = getDesktopBridge();
  const openDataDirectory = async () => {
    if (!runtime || !bridge) return;
    setOpenError(null);
    const result = await bridge.openPath(runtime.dataDir);
    if (!result.ok) setOpenError(result.error || "无法打开数据目录");
  };

  return (
    <div className="space-y-4">
      <SectionCard title="数据目录" description="数据目录由桌面启动参数决定，P0 只读展示，不提供迁移或删除入口。">
        <div className="space-y-4 pt-3">
          <div>
            <div className="text-sm font-medium">仓库根目录</div>
            <p className="mt-1 break-all font-mono text-xs leading-5 text-foreground">{snapshot.settings.storage.repos_dir}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">修改仓库根目录和既有仓库迁移属于后续配置阶段。</p>
          </div>
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
        </div>
      </SectionCard>
      <RuntimeStatusCard runtime={runtime} sidecarState={sidecarState} />
    </div>
  );
}
