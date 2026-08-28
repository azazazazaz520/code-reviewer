import { useEffect, useState } from "react";
import type { EffectiveSettingsSnapshot } from "../../types/settings";
import { settingsApi } from "../../api/settings";
import { toUserError } from "../../utils/error-message";
import SectionCard from "./SectionCard";
import SecretField from "./SecretField";
import SettingField from "./SettingField";
import { SettingsForm, SettingsInput, type SaveSettings } from "./SettingsForm";

interface ModelSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
  onSaved: SaveSettings;
  onSecretChanged: () => void;
}

export default function ModelSettings({ snapshot, onSaved, onSecretChanged }: ModelSettingsProps) {
  const { llm } = snapshot.settings;
  const [model, setModel] = useState(llm.model);
  const [baseUrl, setBaseUrl] = useState(llm.base_url);
  const [temperature, setTemperature] = useState(String(llm.temperature));
  const [maxTokens, setMaxTokens] = useState(String(llm.max_tokens));
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const source = (path: string) => snapshot.sources[path] === "env" ? "环境配置" : snapshot.sources[path] === "user_file" ? "用户配置" : "默认值";

  useEffect(() => {
    setModel(llm.model);
    setBaseUrl(llm.base_url);
    setTemperature(String(llm.temperature));
    setMaxTokens(String(llm.max_tokens));
  }, [llm.base_url, llm.max_tokens, llm.model, llm.temperature]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await onSaved({
        llm: {
          model: model.trim(),
          base_url: baseUrl.trim(),
          temperature: Number(temperature),
          max_tokens: Number(maxTokens),
        },
      });
      setMessage("模型服务设置已保存");
    } catch (saveError) {
      setError(toUserError(saveError, "模型服务设置保存失败，请检查输入后重试。").message);
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setTestMessage(null);
    setError(null);
    try {
      const response = await settingsApi.testLlm({
        model: model.trim(),
        base_url: baseUrl.trim(),
        temperature: Number(temperature),
        max_tokens: Number(maxTokens),
      });
      setTestMessage(response.data.message);
    } catch (testError) {
      setError(toUserError(testError, "模型服务连接失败，请检查配置后重试。").message);
    } finally {
      setTesting(false);
    }
  };

  return (
    <SectionCard title="模型服务" description="配置模型服务地址、模型和生成参数。保存后，新建的 Prompt 请求使用最新设置。">
      <SettingsForm onSubmit={save} saving={saving} message={message} error={error}>
        <div className="flex items-start gap-3 border-b border-border/70 py-4">
          <SettingField label="服务类型" value="OpenAI 兼容模型服务" description="可连接符合 OpenAI API 规范的模型服务。" />
        </div>
        <SettingsInput label="模型" value={model} onChange={setModel} description={`当前来源：${source("llm.model")}`} />
        <SettingsInput label="Base URL" value={baseUrl} onChange={setBaseUrl} description={`当前来源：${source("llm.base_url")}`} />
        <SettingsInput label="Temperature" type="number" min={0} max={2} step={0.1} value={temperature} onChange={setTemperature} description="控制生成结果的随机程度，范围为 0～2。" />
        <SettingsInput label="最大输出 Token" type="number" min={1} max={100000} value={maxTokens} onChange={setMaxTokens} description="限制单次模型响应的最大长度。" />
        <div className="flex flex-wrap items-center gap-3 border-b border-border/70 py-4">
          <button type="button" className="min-h-10 rounded-lg border border-border px-3 text-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50" onClick={() => void testConnection()} disabled={testing || saving}>
            {testing ? "测试中…" : "测试模型服务"}
          </button>
          {testMessage && <span className="text-xs text-primary" role="status">{testMessage}</span>}
        </div>
      </SettingsForm>
      <div className="pt-2">
        <h3 className="text-sm font-medium">访问凭据</h3>
        <div className="mt-1">
          <SecretField
            label="模型服务 API Key"
            provider="llm"
            state={snapshot.secret_status.llm_api_key}
            description="密钥仅用于连接模型服务，不会在页面回显。"
            onChanged={onSecretChanged}
          />
        </div>
      </div>
    </SectionCard>
  );
}
