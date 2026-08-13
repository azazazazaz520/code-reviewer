import type { EffectiveSettingsSnapshot } from "../../types/settings";
import SectionCard from "./SectionCard";
import SettingField from "./SettingField";

interface PromptSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
}

export default function PromptSettings({ snapshot }: PromptSettingsProps) {
  const { prompt } = snapshot.settings;
  const source = (path: string) => snapshot.sources[path] === "env" ? "环境配置" : snapshot.sources[path] === "user_file" ? "用户配置文件" : "默认值";
  return (
    <SectionCard title="提示词工作台" description="查看请求、输入和本地审查会话的限制。新会话和新请求使用当前进程的有效配置。">
      <div className="pt-1">
        <SettingField label="请求超时" value={`${prompt.timeout_seconds} 秒`} source={source("prompt.timeout_seconds")} />
        <SettingField label="最小输入长度" value={`${prompt.min_input_chars} 个字符`} source={source("prompt.min_input_chars")} />
        <SettingField label="最大输入长度" value={`${prompt.max_input_chars} 个字符`} source={source("prompt.max_input_chars")} />
        <SettingField label="最大输出 Token" value={prompt.max_output_tokens} source={source("prompt.max_output_tokens")} />
        <SettingField label="会话 TTL" value={`${prompt.session_ttl_seconds} 秒`} source={source("prompt.session_ttl_seconds")} />
        <SettingField label="会话数量上限" value={prompt.session_max_count} source={source("prompt.session_max_count")} />
        <SettingField label="会话上下文上限" value={`${prompt.session_max_context_chars} 个字符`} source={source("prompt.session_max_context_chars")} />
      </div>
    </SectionCard>
  );
}
