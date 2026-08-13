import { CheckCircle2, CircleAlert, CircleDashed, LoaderCircle } from "lucide-react";
import type { DesktopRuntimeInfo, SidecarState } from "../../runtime/desktop";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";

interface RuntimeStatusCardProps {
  runtime: DesktopRuntimeInfo | null;
  sidecarState: SidecarState | null;
}

function statusText(state: SidecarState | null): string {
  if (!state) return "未接入桌面运行时";
  if (state.status === "ready") return "运行正常";
  if (state.status === "starting") return "正在启动";
  if (state.status === "failed") return "启动失败";
  return "已停止";
}

export default function RuntimeStatusCard({ runtime, sidecarState }: RuntimeStatusCardProps) {
  const status = sidecarState?.status;
  const Icon = status === "ready" ? CheckCircle2 : status === "starting" ? LoaderCircle : status === "failed" ? CircleAlert : CircleDashed;
  const iconClass = status === "ready" ? "text-primary" : status === "failed" ? "text-destructive" : "text-muted-foreground";
  return (
    <Card className="border-border/80 shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">运行状态</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${iconClass} ${status === "starting" ? "animate-spin" : ""}`} aria-hidden="true" />
          <span>{statusText(sidecarState)}</span>
        </div>
        {sidecarState?.status === "failed" && <p className="text-xs leading-5 text-destructive">{sidecarState.message}</p>}
        <dl className="space-y-2 text-xs text-muted-foreground">
          <div className="flex items-start justify-between gap-3"><dt>运行模式</dt><dd className="text-right text-foreground">{runtime?.mode === "production" ? "桌面生产模式" : runtime ? "桌面开发模式" : "浏览器模式"}</dd></div>
          <div className="flex items-start justify-between gap-3"><dt>API 地址</dt><dd className="max-w-[65%] break-all text-right font-mono text-foreground">{runtime?.apiBaseUrl || "由浏览器代理"}</dd></div>
        </dl>
      </CardContent>
    </Card>
  );
}
