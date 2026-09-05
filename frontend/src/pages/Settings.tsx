import { useState } from "react";
import { RefreshCw, Settings as SettingsIcon } from "lucide-react";
import ErrorNotice from "../components/ErrorNotice";
import { Card, CardContent } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { useSettings } from "../hooks/use-settings";
import type { SettingsSection } from "../types/settings";
import SettingsNavigation from "../components/settings/SettingsNavigation";
import AppearanceSettings from "../components/settings/AppearanceSettings";
import ModelSettings from "../components/settings/ModelSettings";
import GitHostSettings from "../components/settings/GitHostSettings";
import ReviewSettings from "../components/settings/ReviewSettings";
import PromptSettings from "../components/settings/PromptSettings";
import StorageSettings from "../components/settings/StorageSettings";
import AboutSettings from "../components/settings/AboutSettings";

const sectionTitles: Record<SettingsSection, string> = {
  appearance: "常规与外观",
  model: "模型服务",
  git: "代码托管",
  review: "审查行为",
  prompt: "Prompt 工具箱",
  storage: "数据与诊断",
  about: "关于",
};

function LoadingState() {
  return (
    <div className="space-y-4" aria-label="正在加载设置" aria-busy="true">
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

export default function Settings() {
  const [activeSection, setActiveSection] = useState<SettingsSection>("appearance");
  const { snapshot, runtime, sidecarState, runtimeError, loading, error, reload, save } = useSettings();

  const renderSection = () => {
    if (!snapshot) return null;
    switch (activeSection) {
      case "appearance": return <AppearanceSettings />;
      case "model": return <ModelSettings snapshot={snapshot} onSaved={save} onSecretChanged={reload} />;
      case "git": return <GitHostSettings snapshot={snapshot} onChanged={reload} />;
      case "review": return <ReviewSettings snapshot={snapshot} onSaved={save} />;
      case "prompt": return <PromptSettings snapshot={snapshot} onSaved={save} />;
      case "storage": return <StorageSettings snapshot={snapshot} runtime={runtime} sidecarState={sidecarState} onSaved={save} />;
      case "about": return <AboutSettings snapshot={snapshot} runtime={runtime} />;
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="mt-1 rounded-lg bg-primary/10 p-2 text-primary">
            <SettingsIcon className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">设置</h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">管理模型、审查、仓库连接和本地运行状态。</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-live="polite">
          {loading ? "正在读取当前配置" : snapshot ? "已读取当前有效配置" : "尚未读取配置"}
          <button
            type="button"
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-border bg-background transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:opacity-50"
            onClick={reload}
            disabled={loading}
            aria-label="重新读取设置"
            title="重新读取设置"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
          </button>
        </div>
      </header>

      {error && <ErrorNotice error={error} title="设置读取失败" onRetry={reload} />}
      {runtimeError && !error && <ErrorNotice error={runtimeError} title="桌面运行时信息不可用" compact />}

      {loading && !snapshot ? <LoadingState /> : snapshot ? (
        <div className="grid gap-6 md:grid-cols-[minmax(13rem,8rem)_minmax(0,1fr)]">
          <aside className="md:sticky md:top-6 md:self-start">
            <SettingsNavigation activeSection={activeSection} onChange={setActiveSection} />
          </aside>
          <section aria-labelledby="settings-section-title" className="min-w-0">
            <h2 id="settings-section-title" className="sr-only">{sectionTitles[activeSection]}</h2>
            {renderSection()}
          </section>
        </div>
      ) : (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">当前没有可展示的设置快照。</CardContent>
        </Card>
      )}
    </div>
  );
}
