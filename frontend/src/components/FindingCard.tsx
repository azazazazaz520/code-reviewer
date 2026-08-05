import { useId, useState } from "react";
import { Copy, ChevronDown } from "lucide-react";
import type { Finding } from "../types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";
import { getSeverityConfig } from "../lib/severity";

interface FindingCardProps {
  finding: Finding;
  defaultOpen?: boolean;
}

function copyFinding(f: Finding) {
  const text = `[${f.severity.toUpperCase()}] ${f.file}:${f.line} — ${f.title}\n原因：${f.reason}\n建议：${f.suggestion}`;
  navigator.clipboard.writeText(text).catch(() => {});
}

export default function FindingCard({
  finding,
  defaultOpen = false,
}: FindingCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();
  const config = getSeverityConfig(finding.severity);
  const Icon = config.icon;

  return (
    <Card className={`border-l-[3px] ${config.borderColor} mb-2`}>
      <CardHeader className="p-3 pb-0">
        <div className="flex items-center justify-between gap-2">
          <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md text-left select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-controls={contentId}
        >
            <Badge variant={config.badgeVariant}>
              <Icon className="h-3 w-3" />
              {config.label}
            </Badge>
            {finding.evidence_type === "reviewer_context" && (
              <Badge variant="outline" className="text-muted-foreground">
                修改附近
              </Badge>
            )}
            <span className="font-mono text-sm text-foreground/80 truncate">
              {finding.file}
              <span className="text-muted-foreground text-xs ml-1">
                :{finding.line}
              </span>
            </span>
            <span className="text-sm font-medium text-foreground truncate hidden sm:inline">
              — {finding.title}
            </span>
          </button>

          <div className="flex items-center gap-1 shrink-0 ml-2">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={(e) => {
                e.stopPropagation();
                copyFinding(finding);
              }}
              title="复制到剪贴板"
              aria-label="复制发现项"
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
            <button
              type="button"
              className="rounded-md p-1 text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpen(!open)}
              aria-expanded={open}
              aria-controls={contentId}
              aria-label={open ? "收起发现项" : "展开发现项"}
            >
              <ChevronDown
              className={`h-4 w-4 text-muted-foreground transition-transform duration-150 ${
                open ? "rotate-180" : ""
              }`}
              />
            </button>
          </div>
        </div>
        {/* Show title below on mobile where it might be truncated above */}
        <p className="text-sm font-medium mt-1 sm:hidden">{finding.title}</p>
      </CardHeader>

      {open && (
        <CardContent id={contentId} className="p-3 pt-2 space-y-2">
          <p className="text-sm text-muted-foreground">
            <strong className="text-foreground">原因：</strong>
            {finding.reason}
          </p>
          <div className="rounded-md bg-muted p-3 text-sm font-mono border-l-2 border-primary">
            <span className="text-muted-foreground">建议：</span>
            <span className="text-primary">{finding.suggestion}</span>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
