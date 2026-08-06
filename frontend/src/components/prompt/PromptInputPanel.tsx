import type { PromptMode, PromptPersona } from "../../types/prompt";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";

interface PromptInputPanelProps {
  content: string;
  persona: PromptPersona;
  mode: PromptMode;
  glossaryEnabled: boolean;
  loading: boolean;
  onContentChange: (value: string) => void;
  onPersonaChange: (value: PromptPersona) => void;
  onModeChange: (value: PromptMode) => void;
  onGlossaryChange: (value: boolean) => void;
  onSubmit: () => void;
}
const personas: Array<{ value: PromptPersona; label: string }> = [
  { value: "general", label: "通用研发沟通" },
  { value: "frontend", label: "前端开发" },
  { value: "backend", label: "后端开发" },
  { value: "ui", label: "界面与交互" },
  { value: "qa", label: "测试与质量" },
  { value: "architecture", label: "架构评审" },
];

export default function PromptInputPanel(props: PromptInputPanelProps) {
  const remaining = 12000 - props.content.length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>输入研发描述</CardTitle>
        <CardDescription>
          粘贴需求、Bug、日志或文本化截图说明，系统会整理为可协作的结构化内容。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label htmlFor="prompt-content" className="text-sm font-medium">原始描述</label>
          <textarea
            id="prompt-content"
            value={props.content}
            onChange={(event) => props.onContentChange(event.target.value)}
            placeholder="例如：点击切换后看起来还是选中，刷新页面又恢复了……"
            className="mt-1 min-h-64 w-full resize-y rounded-md border bg-background px-3 py-2 text-sm leading-6 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            maxLength={12000}
            aria-describedby="prompt-content-help"
          />
          <div id="prompt-content-help" className="mt-1 flex justify-between text-xs text-muted-foreground">
            <span>建议包含操作、现象、预期和复现条件。</span>
            <span>{remaining} 字符可用</span>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="prompt-persona" className="text-sm font-medium">目标接收人</label>
            <select
              id="prompt-persona"
              value={props.persona}
              onChange={(event) => props.onPersonaChange(event.target.value as PromptPersona)}
              className="mt-1 flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
            >
              {personas.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </div>
          <div>
            <span className="text-sm font-medium">生成模式</span>
            <div className="mt-1 flex h-9 rounded-md border" role="group" aria-label="生成模式">
              <button
                type="button"
                className={`flex-1 rounded-l-md px-3 text-sm ${props.mode === "instant" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                onClick={() => props.onModeChange("instant")}
                aria-pressed={props.mode === "instant"}
              >
                直接生成
              </button>
              <button
                type="button"
                className={`flex-1 rounded-r-md px-3 text-sm ${props.mode === "review" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                onClick={() => props.onModeChange("review")}
                aria-pressed={props.mode === "review"}
              >
                逐步审查
              </button>
            </div>
          </div>
        </div>

        <label className="flex items-start gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={props.glossaryEnabled}
            onChange={(event) => props.onGlossaryChange(event.target.checked)}
            className="mt-0.5"
          />
          <span>启用内置术语候选。候选术语会交给模型结合上下文判断，不会直接替换原文。</span>
        </label>

        <Button className="w-full" onClick={props.onSubmit} disabled={props.loading || props.content.trim().length === 0}>
          {props.loading ? "生成中..." : props.mode === "review" ? "生成并开始审查" : "生成结构化结果"}
        </Button>
      </CardContent>
    </Card>
  );
}
