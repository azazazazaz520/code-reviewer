import { useState } from "react";
import { Check, Clipboard, Download } from "lucide-react";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import type { PromptResult } from "../../types/prompt";

type OutputTab = "structured" | "view" | "team" | "terms";

function formatResult(result: PromptResult, format: "markdown" | "jira" | "issue") {
  const solutions = result.solution.map((item, index) => {
    const prefix = format === "jira" ? "* " : format === "issue" ? "- [ ] " : `${index + 1}. `;
    return `${prefix}${item}`;
  }).join("\n");
  if (format === "jira") {
    return `h2. 问题现象\n${result.problem_phenomenon}\n\nh2. 技术本质\n${result.technical_essence}\n\nh2. 解决方案\n${solutions}\n\nh2. 沟通摘要\n${result.team_message}`;
  }
  if (format === "issue") {
    const checks = result.checks.map((item) => `- [ ] ${item}`).join("\n") || "- [ ] 无";
    return `## 问题描述\n${result.problem_phenomenon}\n\n## 技术背景\n${result.technical_essence}\n\n## 实施清单\n${solutions}\n\n## 验收与待确认\n${checks}\n\n## 沟通摘要\n${result.team_message}`;
  }
  const terms = result.term_mappings.map((item) => `- ${item.original} → **${item.professional}**：${item.reason}`).join("\n") || "- 无候选术语映射";
  return `# ${result.team_message}\n\n## 问题现象\n${result.problem_phenomenon}\n\n## 技术本质\n${result.technical_essence}\n\n## 解决方案\n${solutions}\n\n## 分类\n${result.classification.type}（置信度 ${(result.classification.confidence * 100).toFixed(0)}%）\n${result.classification.reason}\n\n## Bug 视角\n${result.bug_view}\n\n## 需求视角\n${result.prd_view}\n\n## 术语对照\n${terms}`;
}

function downloadText(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

interface PromptOutputPanelProps {
  result: PromptResult | null;
}

export default function PromptOutputPanel({ result }: PromptOutputPanelProps) {
  const [tab, setTab] = useState<OutputTab>("structured");
  const [feedback, setFeedback] = useState<string | null>(null);

  if (!result) {
    return (
      <Card className="min-h-[28rem]">
        <CardContent className="flex h-full min-h-[28rem] items-center justify-center text-center text-sm text-muted-foreground">
          结构化结果会显示在这里
        </CardContent>
      </Card>
    );
  }

  const copy = async (format: "markdown" | "jira" | "issue") => {
    const labels = { markdown: "Markdown", jira: "Jira 文本", issue: "Issue 模板" };
    await navigator.clipboard.writeText(formatResult(result, format));
    setFeedback(`已复制 ${labels[format]}`);
    window.setTimeout(() => setFeedback(null), 1800);
  };

  return (
    <Card>
      <CardHeader className="gap-3 border-b">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>结构化结果</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">结果已通过服务端 JSON 契约校验，可直接复制或下载。</p>
          </div>
          <Badge variant="outline">{result.classification.type}</Badge>
        </div>
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="结果视角">
          {(["structured", "view", "team", "terms"] as OutputTab[]).map((item) => {
            const labels = { structured: "结构化结果", view: "Bug / 需求视角", team: "团队沟通版", terms: "术语对照" };
            return <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => setTab(item)} className={`rounded-md px-3 py-1.5 text-sm ${tab === item ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}>{labels[item]}</button>;
          })}
        </div>
      </CardHeader>
      <CardContent className="space-y-5 pt-5">
        {tab === "structured" && <>
          <section><h3 className="mb-1 text-sm font-semibold">问题现象</h3><p className="whitespace-pre-wrap text-sm leading-6">{result.problem_phenomenon}</p></section>
          <section><h3 className="mb-1 text-sm font-semibold">技术本质</h3><p className="whitespace-pre-wrap text-sm leading-6">{result.technical_essence}</p></section>
          <section><h3 className="mb-2 text-sm font-semibold">解决方案</h3><ol className="list-decimal space-y-2 pl-5 text-sm leading-6">{result.solution.map((item) => <li key={item}>{item}</li>)}</ol></section>
        </>}
        {tab === "view" && <div className="space-y-5"><section><h3 className="mb-1 text-sm font-semibold">Bug 视角</h3><p className="whitespace-pre-wrap text-sm leading-6">{result.bug_view}</p></section><section><h3 className="mb-1 text-sm font-semibold">需求视角</h3><p className="whitespace-pre-wrap text-sm leading-6">{result.prd_view}</p></section></div>}
        {tab === "team" && <div className="rounded-lg bg-muted/50 p-5 text-base leading-7">{result.team_message}</div>}
        {tab === "terms" && <div className="space-y-3">{result.term_mappings.length ? result.term_mappings.map((item) => <div key={`${item.original}-${item.professional}`} className="rounded-md border p-3 text-sm"><div><span className="text-muted-foreground">原始表达：</span>{item.original}</div><div><span className="text-muted-foreground">专业术语：</span>{item.professional}</div><div className="mt-1 text-muted-foreground">依据：{item.reason}</div></div>) : <p className="text-sm text-muted-foreground">本次没有识别到需要映射的术语。</p>}</div>}

        {(result.checks.length > 0 || result.assumptions.length > 0) && <div className="space-y-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm"><h3 className="font-semibold">待确认信息</h3>{result.checks.map((item) => <p key={item} className="text-muted-foreground">检查：{item}</p>)}{result.assumptions.map((item) => <p key={item} className="text-muted-foreground">前提：{item}</p>)}</div>}

        <div className="flex flex-wrap items-center gap-2 border-t pt-4">
          <Button size="sm" variant="outline" onClick={() => void copy("markdown")}><Clipboard className="h-4 w-4" />复制 Markdown</Button>
          <Button size="sm" variant="outline" onClick={() => void copy("jira")}><Clipboard className="h-4 w-4" />复制 Jira 文本</Button>
          <Button size="sm" variant="outline" onClick={() => void copy("issue")}><Clipboard className="h-4 w-4" />复制 Issue 模板</Button>
          <Button size="sm" variant="ghost" onClick={() => downloadText("prompt-result.md", formatResult(result, "markdown"))}><Download className="h-4 w-4" />下载</Button>
          {feedback && <span className="flex items-center gap-1 text-xs text-muted-foreground"><Check className="h-3.5 w-3.5" />{feedback}</span>}
        </div>
      </CardContent>
    </Card>
  );
}
