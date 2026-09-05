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
      </div>
    </SectionCard>
  );
}
