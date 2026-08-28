import { useEffect, useRef, useState } from "react";
import PromptInputPanel from "../components/prompt/PromptInputPanel";
import PromptOutputPanel from "../components/prompt/PromptOutputPanel";
import PromptReviewStepper from "../components/prompt/PromptReviewStepper";
import { promptApi } from "../api/prompts";
import type { PromptMode, PromptOptimizeResponse, PromptPersona } from "../types/prompt";
import ErrorNotice from "../components/ErrorNotice";
import { toUserError, type UserErrorInfo } from "../utils/error-message";
export default function PromptWorkbench() {
  const [content, setContent] = useState("");
  const [persona, setPersona] = useState<PromptPersona>("general");
  const [mode, setMode] = useState<PromptMode>("instant");
  const [glossaryEnabled, setGlossaryEnabled] = useState(true);
  const [response, setResponse] = useState<PromptOptimizeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<UserErrorInfo | null>(null);
  const latestRequest = useRef(0);
  const sessionId = useRef<string | null>(null);

  const requestKey = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;

  const applyResponse = (nextResponse: PromptOptimizeResponse) => {
    sessionId.current = nextResponse.session_id;
    setResponse(nextResponse);
  };

  useEffect(() => () => {
    if (sessionId.current) {
      void promptApi.removeSession(sessionId.current).catch(() => undefined);
    }
  }, []);

  const generate = async () => {
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    const previousSessionId = sessionId.current;
    sessionId.current = null;
    if (previousSessionId) {
      void promptApi.removeSession(previousSessionId).catch(() => undefined);
    }
    setLoading(true);
    setError(null);
    try {
      const result = await promptApi.optimize({
        content,
        persona,
        mode,
        glossary_enabled: glossaryEnabled,
        idempotency_key: mode === "review" ? requestKey() : undefined,
      });
      if (latestRequest.current === requestId) {
        applyResponse(result.data);
      }
    } catch (requestError) {
      if (latestRequest.current === requestId) {
        setError(toUserError(requestError, "生成失败，请稍后重试"));
      }
    } finally {
      if (latestRequest.current === requestId) {
        setLoading(false);
      }
    }
  };

  const submitFeedback = async (feedback: string): Promise<boolean> => {
    if (!response?.session_id) return false;
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    const currentResponse = response;
    const currentSessionId = currentResponse.session_id;
    if (!currentSessionId) return false;
    setLoading(true);
    setError(null);
    try {
      const result = await promptApi.addTurn(
        currentSessionId,
        feedback,
        currentResponse.turn,
        requestKey(),
      );
      if (latestRequest.current === requestId) {
        applyResponse(result.data);
      }
      return true;
    } catch (requestError) {
      if (latestRequest.current === requestId) {
        setError(toUserError(requestError, "更新审查结果失败，请重新生成"));
      }
      return false;
    } finally {
      if (latestRequest.current === requestId) {
        setLoading(false);
      }
    }
  };

  const restart = () => {
    latestRequest.current += 1;
    const previousSessionId = sessionId.current;
    sessionId.current = null;
    if (previousSessionId) {
      void promptApi.removeSession(previousSessionId).catch(() => undefined);
    }
    setResponse(null);
    setError(null);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Prompt 工具箱</h1>
        <p className="mt-1 text-sm text-muted-foreground">将口语化研发描述整理为清晰、可执行、可沟通的结构化内容。</p>
      </div>
      {error && <ErrorNotice error={error} />}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(20rem,0.8fr)_minmax(32rem,1.2fr)]">
        <div className="space-y-4">
          <PromptInputPanel content={content} persona={persona} mode={mode} glossaryEnabled={glossaryEnabled} loading={loading} onContentChange={setContent} onPersonaChange={setPersona} onModeChange={setMode} onGlossaryChange={setGlossaryEnabled} onSubmit={() => void generate()} />
          {response?.session_id && mode === "review" && <PromptReviewStepper response={response} loading={loading} onSubmit={submitFeedback} onRestart={restart} />}
        </div>
          <PromptOutputPanel result={response?.result || null} exports={response?.exports || null} />
      </div>
    </div>
  );
}
