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
  const [batchMaxChars, setBatchMaxChars] = useState(String(review.review_batch_max_chars));
  const [contextMaxFiles, setContextMaxFiles] = useState(String(review.review_context_max_files));
  const [contextMaxChars, setContextMaxChars] = useState(String(review.review_context_max_chars));
  const [supplementMaxChars, setSupplementMaxChars] = useState(String(review.supplement_context_max_chars));
  const [paddingLines, setPaddingLines] = useState(String(review.review_context_padding_lines));
  const [maxDuration, setMaxDuration] = useState(String(review.max_review_duration_seconds));
  const [parallelism, setParallelism] = useState(String(review.review_parallelism));
  const [crgEnabled, setCrgEnabled] = useState(review.crg_enabled);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBatchMaxChars(String(review.review_batch_max_chars));
    setContextMaxFiles(String(review.review_context_max_files));
    setContextMaxChars(String(review.review_context_max_chars));
    setSupplementMaxChars(String(review.supplement_context_max_chars));
    setPaddingLines(String(review.review_context_padding_lines));
    setMaxDuration(String(review.max_review_duration_seconds));
    setParallelism(String(review.review_parallelism));
    setCrgEnabled(review.crg_enabled);
  }, [review]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await onSaved({
        review: {
          review_batch_max_chars: Number(batchMaxChars),
          review_context_max_files: Number(contextMaxFiles),
          review_context_max_chars: Number(contextMaxChars),
          supplement_context_max_chars: Number(supplementMaxChars),
          review_context_padding_lines: Number(paddingLines),
          max_review_duration_seconds: Number(maxDuration),
          review_parallelism: Number(parallelism),
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
    <SectionCard title="审查行为" description="调整批次大小、上下文和执行时限。默认流程不使用多轮 Tool 或 Reflection。">
      <SettingsForm onSubmit={save} saving={saving} message={message} error={error}>
        <SettingsInput label="批次最大字符数" type="number" min={8000} max={100000} value={batchMaxChars} onChange={setBatchMaxChars} description="同一 Reviewer 合并变更时的目标 Diff 大小；完整 Hunk 不会被拆分。" />
        <SettingsInput label="上下文最大文件数" type="number" min={1} max={20} value={contextMaxFiles} onChange={setContextMaxFiles} description="单个审查批次可携带的聚焦上下文文件数量，最多 20 个。" />
        <SettingsInput label="上下文最大字符数" type="number" min={8000} max={60000} value={contextMaxChars} onChange={setContextMaxChars} description="主要审查请求可携带的聚焦代码上下文上限。" />
        <SettingsInput label="补充上下文最大字符数" type="number" min={1000} max={60000} value={supplementMaxChars} onChange={setSupplementMaxChars} description="模型一次性申请补充上下文时允许返回的总字符数。" />
        <SettingsInput label="变更区域前后文行数" type="number" min={0} max={500} value={paddingLines} onChange={setPaddingLines} description="主要审查请求在每个 Hunk 两侧预取的源码行数。" />
        <SettingsInput label="任务最大执行秒数" type="number" min={60} max={7200} value={maxDuration} onChange={setMaxDuration} description="异常任务达到时限后停止启动新的 Reviewer 批次。" />
        <SettingsInput label="Reviewer 并行数" type="number" min={1} max={8} value={parallelism} onChange={setParallelism} description="独立 Reviewer 同时执行的最大数量。" />
        <label className="flex cursor-pointer items-start gap-3 border-b border-border/70 py-4">
          <input type="checkbox" className="mt-1 h-4 w-4 accent-primary" checked={crgEnabled} onChange={(event) => setCrgEnabled(event.target.checked)} />
          <span>
            <span className="block text-sm font-medium">启用深度审查</span>
            <span className="mt-1 block text-xs leading-5 text-muted-foreground">显式建立代码数据库并运行 CRG，适用于大规模重构和跨文件影响分析。</span>
          </span>
        </label>
      </SettingsForm>
    </SectionCard>
  );
}
