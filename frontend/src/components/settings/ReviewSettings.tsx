import { useEffect, useState } from "react";
import type { EffectiveSettingsSnapshot } from "../../types/settings";
import { toUserError } from "../../utils/error-message";
import SectionCard from "./SectionCard";
import { SettingsForm, SettingsInput, type SaveSettings } from "./SettingsForm";

interface ReviewSettingsProps {
  snapshot: EffectiveSettingsSnapshot;
  onSaved: SaveSettings;
}

export default function ReviewSettings({ snapshot, onSaved }: ReviewSettingsProps) {
  const { review } = snapshot.settings;
  const [maxRounds, setMaxRounds] = useState(String(review.max_reflection_rounds));
  const [filesPerRound, setFilesPerRound] = useState(String(review.context_files_per_round));
  const [crgEnabled, setCrgEnabled] = useState(review.crg_enabled);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMaxRounds(String(review.max_reflection_rounds));
    setFilesPerRound(String(review.context_files_per_round));
    setCrgEnabled(review.crg_enabled);
  }, [review.context_files_per_round, review.crg_enabled, review.max_reflection_rounds]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await onSaved({
        review: {
          max_reflection_rounds: Number(maxRounds),
          context_files_per_round: Number(filesPerRound),
          crg_enabled: crgEnabled,
        },
      });
      setMessage("审查设置已保存");
    } catch (saveError) {
      setError(toUserError(saveError, "审查设置保存失败，请检查输入后重试。").message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard title="审查行为" description="调整新建代码审查使用的上下文与执行策略。">
      <SettingsForm onSubmit={save} saving={saving} message={message} error={error}>
        <SettingsInput label="最大反思轮数" type="number" min={1} max={20} value={maxRounds} onChange={setMaxRounds} description="限制审查反思阶段的最大执行轮次。" />
        <SettingsInput label="每轮上下文文件数" type="number" min={1} max={200} value={filesPerRound} onChange={setFilesPerRound} description="每轮加入审查上下文的文件数量。" />
        <label className="flex cursor-pointer items-start gap-3 border-b border-border/70 py-4">
          <input type="checkbox" className="mt-1 h-4 w-4 accent-primary" checked={crgEnabled} onChange={(event) => setCrgEnabled(event.target.checked)} />
          <span>
            <span className="block text-sm font-medium">启用结构化上下文</span>
            <span className="mt-1 block text-xs leading-5 text-muted-foreground">为审查补充结构性影响信息，帮助确定需要关注的审查范围。</span>
          </span>
        </label>
      </SettingsForm>
    </SectionCard>
  );
}
