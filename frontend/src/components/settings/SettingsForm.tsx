import type { FormEvent, ReactNode } from "react";
import { CheckCircle2, Save } from "lucide-react";
import { Button } from "../ui/button";
import type { SettingsPatch, SettingsUpdateResponse } from "../../types/settings";

export const settingInputClassName =
  "min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30";

export type SaveSettings = (patch: SettingsPatch) => Promise<SettingsUpdateResponse>;

interface SettingsFormProps {
  onSubmit: (event: FormEvent<HTMLFormElement>) => void | Promise<void>;
  saving: boolean;
  message: string | null;
  error: string | null;
  children: ReactNode;
}

export function SettingsForm({ onSubmit, saving, message, error, children }: SettingsFormProps) {
  return (
    <form onSubmit={(event) => void onSubmit(event)} className="space-y-1">
      {children}
      <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border/70 pt-4">
        {message && (
          <span className="mr-auto inline-flex items-center gap-1.5 text-xs text-primary" role="status">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            {message}
          </span>
        )}
        {error && <span className="mr-auto text-xs text-destructive" role="alert">{error}</span>}
        <Button type="submit" disabled={saving} className="min-h-11">
          <Save className="h-4 w-4" aria-hidden="true" />
          {saving ? "保存中…" : "保存设置"}
        </Button>
      </div>
    </form>
  );
}

interface SettingsInputProps {
  label: string;
  description?: string;
  type?: "text" | "number";
  value: string | number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: string) => void;
}

export function SettingsInput({ label, description, type = "text", value, min, max, step, onChange }: SettingsInputProps) {
  return (
    <label className="grid gap-2 border-b border-border/70 py-4 last:border-b-0 sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] sm:items-center sm:gap-6">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {description && <span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span>}
      </span>
      <input
        className={settingInputClassName}
        type={type}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
