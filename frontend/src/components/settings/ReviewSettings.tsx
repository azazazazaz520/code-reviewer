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
  const [maxIncrementalRounds, setMaxIncrementalRounds] = useState(String(review.max_incremental_reflection_rounds));
  const [filesPerRound, setFilesPerRound] = useState(String(review.context_files_per_round));
  const [unitMaxChars, setUnitMaxChars] = useState(String(review.review_unit_max_chars));
  const [contextMaxFiles, setContextMaxFiles] = useState(String(review.review_context_max_files));
  const [contextMaxChars, setContextMaxChars] = useState(String(review.review_context_max_chars));
  const [paddingLines, setPaddingLines] = useState(String(review.review_context_padding_lines));
  const [maxReviewCalls, setMaxReviewCalls] = useState(String(review.max_review_calls));
  const [maxDuration, setMaxDuration] = useState(String(review.max_review_duration_seconds));
  const [maxToolRounds, setMaxToolRounds] = useState(String(review.max_tool_rounds));
  const [maxToolCalls, setMaxToolCalls] = useState(String(review.max_tool_calls_per_unit));
  const [maxRelatedFiles, setMaxRelatedFiles] = useState(String(review.max_related_files_per_unit));
  const [parallelism, setParallelism] = useState(String(review.review_parallelism));
  const [crgEnabled, setCrgEnabled] = useState(review.crg_enabled);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMaxRounds(String(review.max_reflection_rounds));
    setMaxIncrementalRounds(String(review.max_incremental_reflection_rounds));
    setFilesPerRound(String(review.context_files_per_round));
    setUnitMaxChars(String(review.review_unit_max_chars));
    setContextMaxFiles(String(review.review_context_max_files));
    setContextMaxChars(String(review.review_context_max_chars));
    setPaddingLines(String(review.review_context_padding_lines));
    setMaxReviewCalls(String(review.max_review_calls));
    setMaxDuration(String(review.max_review_duration_seconds));
    setMaxToolRounds(String(review.max_tool_rounds));
    setMaxToolCalls(String(review.max_tool_calls_per_unit));
    setMaxRelatedFiles(String(review.max_related_files_per_unit));
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
          max_reflection_rounds: Number(maxRounds),
          max_incremental_reflection_rounds: Number(maxIncrementalRounds),
          context_files_per_round: Number(filesPerRound),
          review_unit_max_chars: Number(unitMaxChars),
          review_context_max_files: Number(contextMaxFiles),
          review_context_max_chars: Number(contextMaxChars),
          review_context_padding_lines: Number(paddingLines),
          max_review_calls: Number(maxReviewCalls),
          max_review_duration_seconds: Number(maxDuration),
          max_tool_rounds: Number(maxToolRounds),
          max_tool_calls_per_unit: Number(maxToolCalls),
          max_related_files_per_unit: Number(maxRelatedFiles),
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
    <SectionCard title="审查行为" description="调整新建代码审查使用的上下文与执行策略。">
      <SettingsForm onSubmit={save} saving={saving} message={message} error={error}>
        <SettingsInput label="最大反思轮数" type="number" min={1} max={20} value={maxRounds} onChange={setMaxRounds} description="限制审查反思阶段的最大执行轮次。" />
        <SettingsInput label="增量反思轮数" type="number" min={0} max={10} value={maxIncrementalRounds} onChange={setMaxIncrementalRounds} description="上下文补充后允许新增审查单元的轮数。" />
        <SettingsInput label="每轮上下文文件数" type="number" min={1} max={200} value={filesPerRound} onChange={setFilesPerRound} description="每轮加入审查上下文的文件数量。" />
        <SettingsInput label="单元最大字符数" type="number" min={8000} max={500000} value={unitMaxChars} onChange={setUnitMaxChars} description="单个语义审查单元允许携带的最大 Diff 字符数。" />
        <SettingsInput label="上下文最大文件数" type="number" min={1} max={500} value={contextMaxFiles} onChange={setContextMaxFiles} description="单次审查可放入稳定上下文的文件数量。" />
        <SettingsInput label="上下文最大字符数" type="number" min={8000} max={2000000} value={contextMaxChars} onChange={setContextMaxChars} description="单次审查稳定代码上下文的最大字符数，V4 Flash 支持 1M Token 上下文。" />
        <SettingsInput label="变更区域前后文行数" type="number" min={0} max={500} value={paddingLines} onChange={setPaddingLines} description="变更 Hunk 两侧预取的源码行数。" />
        <SettingsInput label="任务最大模型调用数" type="number" min={1} max={500} value={maxReviewCalls} onChange={setMaxReviewCalls} description="单个任务允许执行的 Reviewer 主调用数。" />
        <SettingsInput label="任务最大执行秒数" type="number" min={60} max={7200} value={maxDuration} onChange={setMaxDuration} description="达到时限后停止新增审查调用并保存部分结果。" />
        <SettingsInput label="单元 Tool 最大轮数" type="number" min={1} max={10} value={maxToolRounds} onChange={setMaxToolRounds} description="单个审查单元允许模型连续请求 Tool 的轮数。" />
        <SettingsInput label="单元 Tool 最大调用数" type="number" min={1} max={20} value={maxToolCalls} onChange={setMaxToolCalls} description="单个审查单元允许的 Tool 请求总数。" />
        <SettingsInput label="单元关联文件数" type="number" min={1} max={20} value={maxRelatedFiles} onChange={setMaxRelatedFiles} description="每个变更单元最多附带的关联文件数。" />
        <SettingsInput label="Reviewer 并行数" type="number" min={1} max={8} value={parallelism} onChange={setParallelism} description="独立 Reviewer 同时执行的最大数量。" />
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
