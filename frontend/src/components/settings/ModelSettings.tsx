import type { EffectiveSettingsSnapshot } from "../../types/settings";
import SectionCard from "./SectionCard";
import SecretField from "./SecretField";
import SettingField from "./SettingField";

interface ModelSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
}

export default function ModelSettings({ snapshot }: ModelSettingsProps) {
  const { llm } = snapshot.settings;
  const source = (path: string) => snapshot.sources[path] === "env" ? "环境配置" : snapshot.sources[path] === "user_file" ? "用户配置文件" : "默认值";
  return (
    <SectionCard title="模型服务" description="当前使用 OpenAI 兼容模型服务。此阶段仅展示已经加载的配置，不提供网页写入入口。">
      <div className="pt-1">
        <SettingField label="服务类型" value="OpenAI 兼容模型服务" description="当前实现使用 DeepSeek 的兼容接口。" />
        <SettingField label="模型" value={llm.model} source={source("llm.model")} />
        <SettingField label="Base URL" value={llm.base_url} source={source("llm.base_url")} />
        <SettingField label="Temperature" value={llm.temperature} source={source("llm.temperature")} />
        <SettingField label="最大输出 Token" value={llm.max_tokens} source={source("llm.max_tokens")} />
        <div className="pt-2">
          <h3 className="text-sm font-medium">凭据状态</h3>
          <div className="mt-1">
            <SecretField label="模型服务 API Key" state={snapshot.secret_status.llm_api_key} description="完整密钥不会返回到页面，也不会显示在诊断信息中。" />
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
