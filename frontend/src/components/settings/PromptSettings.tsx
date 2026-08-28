import { useEffect, useState } from "react";
import type { EffectiveSettingsSnapshot } from "../../types/settings";
import { toUserError } from "../../utils/error-message";
import SectionCard from "./SectionCard";
import { SettingsForm, SettingsInput, type SaveSettings } from "./SettingsForm";

interface PromptSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
  onSaved: SaveSettings;
}

export default function PromptSettings({ snapshot, onSaved }: PromptSettingsProps) {
  const { prompt } = snapshot.settings;
  const [timeout, setTimeoutValue] = useState(String(prompt.timeout_seconds));
  const [minInput, setMinInput] = useState(String(prompt.min_input_chars));
  const [maxInput, setMaxInput] = useState(String(prompt.max_input_chars));
  const [maxOutput, setMaxOutput] = useState(String(prompt.max_output_tokens));
  const [ttl, setTtl] = useState(String(prompt.session_ttl_seconds));
  const [maxSessions, setMaxSessions] = useState(String(prompt.session_max_count));
  const [maxContext, setMaxContext] = useState(String(prompt.session_max_context_chars));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTimeoutValue(String(prompt.timeout_seconds));
    setMinInput(String(prompt.min_input_chars));
    setMaxInput(String(prompt.max_input_chars));
    setMaxOutput(String(prompt.max_output_tokens));
    setTtl(String(prompt.session_ttl_seconds));
    setMaxSessions(String(prompt.session_max_count));
    setMaxContext(String(prompt.session_max_context_chars));
  }, [prompt]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await onSaved({
        prompt: {
          timeout_seconds: Number(timeout),
          min_input_chars: Number(minInput),
          max_input_chars: Number(maxInput),
          max_output_tokens: Number(maxOutput),
          session_ttl_seconds: Number(ttl),
          session_max_count: Number(maxSessions),
          session_max_context_chars: Number(maxContext),
        },
      });
      setMessage("Prompt 工具箱设置已保存");
    } catch (saveError) {
      setError(toUserError(saveError, "Prompt 工具箱设置保存失败，请检查输入后重试。").message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard title="Prompt 工具箱" description="调整输入、输出和本地会话规则。保存后，新建请求按最新设置运行。">
      <SettingsForm onSubmit={save} saving={saving} message={message} error={error}>
        <SettingsInput label="请求超时" type="number" min={1} max={600} value={timeout} onChange={setTimeoutValue} description="单次生成请求的总时间上限，单位为秒。" />
        <SettingsInput label="最小输入长度" type="number" min={1} max={10000} value={minInput} onChange={setMinInput} description="允许提交的最短文本长度。" />
        <SettingsInput label="最大输入长度" type="number" min={1} max={100000} value={maxInput} onChange={setMaxInput} description="允许提交的最长文本长度。" />
        <SettingsInput label="最大输出 Token" type="number" min={1} max={100000} value={maxOutput} onChange={setMaxOutput} description="限制单次结构化结果的最大输出长度。" />
        <SettingsInput label="会话保留时间" type="number" min={60} max={86400} value={ttl} onChange={setTtl} description="未继续操作的会话保留时间，单位为秒。" />
        <SettingsInput label="会话数量上限" type="number" min={1} max={10000} value={maxSessions} onChange={setMaxSessions} description="同时保留的 Prompt 审查会话数量。" />
        <SettingsInput label="会话上下文上限" type="number" min={1} max={500000} value={maxContext} onChange={setMaxContext} description="单个会话允许保留的上下文字符数。" />
      </SettingsForm>
    </SectionCard>
  );
}
