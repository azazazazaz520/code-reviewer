import { CheckCircle2, CircleSlash2 } from "lucide-react";
import { useState } from "react";
import { getDesktopBridge, type SecretProvider } from "../../runtime/desktop";
import type { SecretState } from "../../types/settings";
import { settingInputClassName } from "./SettingsForm";

interface SecretFieldProps {
  label: string;
  state: SecretState;
  description: string;
  provider: SecretProvider;
  onChanged?: () => void;
}

export default function SecretField({ label, state, description, provider, onChanged }: SecretFieldProps) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bridge = getDesktopBridge();
  const configured = state === "configured";

  const save = async () => {
    if (!bridge || !value.trim()) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    const result = await bridge.saveSecret(provider, value);
    setSaving(false);
    if (!result.ok) {
      setError(result.error || "凭据保存失败");
      return;
    }
    setValue("");
    setMessage("已保存并重新连接服务");
    onChanged?.();
  };

  const clear = async () => {
    if (!bridge) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    const result = await bridge.clearSecret(provider);
    setSaving(false);
    if (!result.ok) {
      setError(result.error || "凭据清除失败");
      return;
    }
    setMessage("已清除");
    onChanged?.();
  };

  return (
    <div className="border-b border-border/70 py-4 last:border-b-0">
      <div className="flex items-start gap-3">
        {configured ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        ) : (
          <CircleSlash2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        )}
        <div className="min-w-0">
          <div className="text-sm font-medium">{label}</div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
        </div>
        <span className="ml-auto shrink-0 text-sm text-muted-foreground">{configured ? "已配置" : "未配置"}</span>
      </div>
      {bridge ? (
        <div className="mt-3 flex flex-wrap gap-2 sm:pl-7">
          <input
            className={`${settingInputClassName} min-w-[14rem] flex-1`}
            type="password"
            value={value}
            placeholder={configured ? "输入新密钥以替换" : "输入密钥"}
            autoComplete="new-password"
            onChange={(event) => setValue(event.target.value)}
            aria-label={`${label}输入`}
          />
          <button type="button" className="min-h-11 rounded-lg bg-primary px-3 text-sm text-primary-foreground disabled:pointer-events-none disabled:opacity-50" onClick={() => void save()} disabled={saving || !value.trim()}>
            {saving ? "处理中…" : "保存"}
          </button>
          {configured && (
            <button type="button" className="min-h-11 rounded-lg border border-border px-3 text-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50" onClick={() => void clear()} disabled={saving}>
              清除
            </button>
          )}
        </div>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground sm:pl-7">当前运行环境不支持直接管理密钥，请通过运行环境配置提供。</p>
      )}
      {message && <p className="mt-2 text-xs text-primary sm:pl-7" role="status">{message}</p>}
      {error && <p className="mt-2 text-xs text-destructive sm:pl-7" role="alert">{error}</p>}
    </div>
  );
}
