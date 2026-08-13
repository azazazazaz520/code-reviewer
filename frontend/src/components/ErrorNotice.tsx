import { AlertCircle } from "lucide-react";
import { cn } from "../lib/utils";
import type { UserErrorInfo } from "../utils/error-message";
import { Button } from "./ui/button";

interface ErrorNoticeProps {
  error: UserErrorInfo;
  title?: string;
  onRetry?: () => void;
  className?: string;
  compact?: boolean;
}

export default function ErrorNotice({ error, title = "处理失败", onRetry, className, compact = false }: ErrorNoticeProps) {
  return (
    <div className={cn("rounded-md border border-destructive/30 bg-destructive/5 text-sm", compact ? "p-3" : "p-4", className)} role="alert">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="font-medium text-destructive">{title}</div>
          <p className="text-destructive/90">{error.message}</p>
          {onRetry && (
            <Button variant="outline" size="sm" className="mt-2 min-h-9" onClick={onRetry}>
              重试
            </Button>
          )}
          {error.diagnostic && (
            <details className="mt-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none">查看诊断信息</summary>
              <pre className="mt-1 whitespace-pre-wrap break-words font-mono">{error.diagnostic}</pre>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
