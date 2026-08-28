import { useState } from "react";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import type { PromptOptimizeResponse } from "../../types/prompt";

interface PromptReviewStepperProps {
  response: PromptOptimizeResponse;
  loading: boolean;
  onSubmit: (feedback: string) => Promise<boolean>;
  onRestart: () => void;
}
export default function PromptReviewStepper({ response, loading, onSubmit, onRestart }: PromptReviewStepperProps) {
  const [feedback, setFeedback] = useState("");
  const canContinue = response.turn < response.max_turns && Boolean(response.session_id);
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">审查会话</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span>第 {response.turn} / {response.max_turns} 轮</span>
          {response.expires_at && <span className="text-muted-foreground">有效至 {new Date(response.expires_at).toLocaleString()}</span>}
        </div>
        <p className="text-xs text-muted-foreground">刷新页面或服务重启后，会话可能失效；失效后可重新生成。</p>
        {canContinue ? <>
          <label htmlFor="prompt-review-feedback" className="text-sm font-medium">确认或修正意见</label>
          <textarea id="prompt-review-feedback" value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="例如：补充复现环境，或确认技术本质中的某一项判断" className="min-h-20 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" maxLength={4000} />
          <Button className="w-full" onClick={async () => { if (await onSubmit(feedback)) setFeedback(""); }} disabled={loading || !feedback.trim()}>{loading ? "更新中..." : "提交本轮意见"}</Button>
        </> : <p className="text-sm text-muted-foreground">已达到最大轮次，请重新开始生成。</p>}
        <Button variant="outline" className="w-full" onClick={onRestart}>重新开始</Button>
      </CardContent>
    </Card>
  );
}
