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
    <SectionCard title="关于" description="查看应用版本、运行环境和配置状态。">
      <div className="pt-1">
        <SettingField label="应用版本" value={runtime?.appVersion || "浏览器模式不可读取"} />
        <SettingField label="运行模式" value={runtime ? (runtime.mode === "production" ? "桌面生产模式" : "桌面开发模式") : "浏览器模式"} />
        <SettingField label="配置契约版本" value={`schema v${snapshot.schema_version}`} />
        <SettingField label="用户配置版本" value={snapshot.config_version === 0 ? "尚未保存用户设置" : snapshot.config_version} />
        <div className="mt-4 flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>配置保存后会作用于后续新请求；正在执行的任务继续使用开始执行时的配置。</p>
        </div>
      </div>
    </SectionCard>
  );
}
