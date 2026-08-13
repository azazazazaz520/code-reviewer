import { Info } from "lucide-react";
import type { DesktopRuntimeInfo } from "../../runtime/desktop";
import type { EffectiveSettingsSnapshot } from "../../types/settings";
import SectionCard from "./SectionCard";
import SettingField from "./SettingField";

interface AboutSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
  runtime: DesktopRuntimeInfo | null;
}

export default function AboutSettings({ snapshot, runtime }: AboutSettingsProps) {
  return (
    <SectionCard title="关于" description="用于定位本机运行环境和当前设置快照，不包含凭据或部署参数。">
      <div className="pt-1">
        <SettingField label="应用版本" value={runtime?.appVersion || "浏览器模式不可读取"} />
        <SettingField label="运行模式" value={runtime ? (runtime.mode === "production" ? "桌面生产模式" : "桌面开发模式") : "浏览器模式"} />
        <SettingField label="配置契约版本" value={`schema v${snapshot.schema_version}`} />
        <SettingField label="当前配置版本" value={snapshot.config_version === 0 ? "进程配置（P0 只读）" : snapshot.config_version} />
        <div className="mt-4 flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>本页面当前只读取已经由后端进程加载的配置。配置编辑、连接测试、凭据管理和 sidecar 重启将在后续阶段单独实现。</p>
        </div>
      </div>
    </SectionCard>
  );
}
