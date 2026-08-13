import type { EffectiveSettingsSnapshot } from "../../types/settings";
import SectionCard from "./SectionCard";
import SettingField from "./SettingField";

interface ReviewSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
}

export default function ReviewSettings({ snapshot }: ReviewSettingsProps) {
  const { review } = snapshot.settings;
  const source = (path: string) => snapshot.sources[path] === "env" ? "环境配置" : snapshot.sources[path] === "user_file" ? "用户配置文件" : "默认值";
  return (
    <SectionCard title="审查行为" description="这些值由当前后端进程加载，新建审查按当前有效配置运行。P0 不提供修改入口。">
      <div className="pt-1">
        <SettingField label="最大反思轮数" value={review.max_reflection_rounds} description="限制审查反思阶段的最大执行轮次。" source={source("review.max_reflection_rounds")} />
        <SettingField label="每轮上下文文件数" value={review.context_files_per_round} description="每轮收集到审查上下文中的文件数量。" source={source("review.context_files_per_round")} />
        <SettingField label="结构化上下文策略" value={review.crg_enabled ? "已启用" : "未启用"} description="当前有效配置中的 CRG 开关状态。" source={source("review.crg_enabled")} />
      </div>
    </SectionCard>
  );
}
