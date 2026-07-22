# Phase 1: shadcn/ui Setup + ReviewDetail 页面重写

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Vite + React 19 项目中引入 Tailwind CSS v4 + shadcn/ui，设置双主题 CSS 变量，用 shadcn/ui 组件重写 ReviewDetail 页面（含 ReviewProgress + FindingCard），同时保持 Ant Design Layout 作为外壳继续服务其他页面。

**Architecture:** Ant Design Layout 保留为页面外壳（侧边栏导航），pahse 1 仅替换其 `<Content>` 内部的 ReviewDetail 页面全部组件。shadcn/ui 通过 `components/ui/` 目录按需引入，Tailwind 通过 Vite 插件集成，主题用 CSS 变量定义在 `index.css`。新增 ThemeProvider context 管理亮/暗切换。

**Tech Stack:** React 19, TypeScript 6, Vite 8, Tailwind CSS 4, shadcn/ui (Radix UI), lucide-react, Recharts, react-router-dom 7

## Global Constraints

- **禁止 emoji 作为结构性图标** — 统一使用 lucide-react 的 SVG 图标
- **严重度信息三重编码** — 图标 + 颜色 + 文字标签，不依赖颜色单独传达信息
- **双主题支持** — 所有颜色通过 CSS 变量定义在 `:root` 和 `.dark` 下
- **所有可交互元素** — cursor-pointer + hover 过渡 150ms
- **文件路径** — 使用 `verbatimModuleSyntax`，type-only import 必须用 `import type`
- **Ant Design Layout 保留** — 暂不替换 Sider/Menu/Content，仅替换页面内容区组件

---

### Task 1: 安装依赖

**Files:**
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: 无
- Produces: 新增依赖包供后续 task 使用

- [ ] **Step 1: 安装 Tailwind CSS v4 + 相关包**

```bash
cd E:/code-reviewer/frontend && npm install tailwindcss @tailwindcss/vite lucide-react recharts clsx tailwind-merge
```

Expected: 安装成功，package.json 新增 `tailwindcss`, `@tailwindcss/vite`, `lucide-react`, `recharts`, `clsx`, `tailwind-merge` 依赖

- [ ] **Step 2: 初始化 shadcn/ui**

```bash
cd E:/code-reviewer/frontend && npx shadcn@latest init -d --force
```

如果 shadcn CLI 要求交互，手动选择：TypeScript ✓, CSS Variables ✓, Gray: Neutral, CSS file: src/index.css, 其余默认

Expected: 创建 `src/lib/utils.ts` 和 `components.json`

- [ ] **Step 3: 验证 package.json 依赖完整**

Read `frontend/package.json`，确认包含 `tailwindcss`, `@tailwindcss/vite`, `lucide-react`, `recharts`, `clsx`, `tailwind-merge`, `class-variance-authority`

- [ ] **Step 4: Commit**

```bash
cd E:/code-reviewer/frontend && git add package.json package-lock.json components.json src/lib/ && git commit -m "chore: add Tailwind CSS v4 + shadcn/ui + lucide-react + Recharts"
```

---

### Task 2: 配置 Tailwind + Vite 插件 + CSS 主题

**Files:**
- Modify: `frontend/vite.config.ts`
- Rewrite: `frontend/src/index.css`
- Create: `frontend/postcss.config.js` (如需要)

**Interfaces:**
- Consumes: Task 1 安装的依赖包
- Produces: Tailwind CSS 编译链路 + 双主题 CSS 变量系统

- [ ] **Step 1: 配置 Vite 插件**

Edit `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

- [ ] **Step 2: 重写 `src/index.css` — Tailwind 入口 + 双主题 CSS 变量**

```css
@import "tailwindcss";

@custom-variant dark (&:is(.dark *));

@theme inline {
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
}

:root {
  --radius: 0.625rem;
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.145 0 0);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.145 0 0);
  --primary: oklch(0.5 0.15 155);
  --primary-foreground: oklch(0.985 0 0);
  --secondary: oklch(0.97 0 0);
  --secondary-foreground: oklch(0.205 0 0);
  --muted: oklch(0.97 0 0);
  --muted-foreground: oklch(0.556 0 0);
  --accent: oklch(0.97 0 0);
  --accent-foreground: oklch(0.205 0 0);
  --destructive: oklch(0.56 0.2 25);
  --border: oklch(0.922 0 0);
  --input: oklch(0.922 0 0);
  --ring: oklch(0.5 0.15 155);
  --chart-1: oklch(0.56 0.2 25);
  --chart-2: oklch(0.6 0.18 50);
  --chart-3: oklch(0.65 0.14 85);
  --chart-4: oklch(0.5 0.15 155);
  --chart-5: oklch(0.55 0.12 220);

  /* Severity semantic tokens */
  --severity-critical: oklch(0.56 0.2 25);
  --severity-high: oklch(0.62 0.18 50);
  --severity-medium: oklch(0.65 0.14 85);
  --severity-low: oklch(0.5 0.15 155);
}

.dark {
  --background: oklch(0.16 0.03 260);
  --foreground: oklch(0.95 0.01 260);
  --card: oklch(0.19 0.03 260);
  --card-foreground: oklch(0.95 0.01 260);
  --popover: oklch(0.19 0.03 260);
  --popover-foreground: oklch(0.95 0.01 260);
  --primary: oklch(0.55 0.16 155);
  --primary-foreground: oklch(0.13 0.03 260);
  --secondary: oklch(0.22 0.03 260);
  --secondary-foreground: oklch(0.95 0.01 260);
  --muted: oklch(0.18 0.025 260);
  --muted-foreground: oklch(0.65 0.02 260);
  --accent: oklch(0.22 0.03 260);
  --accent-foreground: oklch(0.95 0.01 260);
  --destructive: oklch(0.56 0.2 25);
  --border: oklch(0.28 0.03 260);
  --input: oklch(0.28 0.03 260);
  --ring: oklch(0.55 0.16 155);

  /* Severity semantic tokens (dark mode — slightly lighter for contrast) */
  --severity-critical: oklch(0.62 0.22 25);
  --severity-high: oklch(0.68 0.19 50);
  --severity-medium: oklch(0.7 0.15 85);
  --severity-low: oklch(0.55 0.16 155);
}

@layer base {
  * { @apply border-border; }
  body {
    @apply bg-background text-foreground;
    margin: 0;
  }
  #root { width: 100%; min-height: 100vh; }
}

@utility bg-severity-critical { background-color: var(--severity-critical); }
@utility bg-severity-high { background-color: var(--severity-high); }
@utility bg-severity-medium { background-color: var(--severity-medium); }
@utility bg-severity-low { background-color: var(--severity-low); }
@utility border-l-severity-critical { border-left-color: var(--severity-critical); }
@utility border-l-severity-high { border-left-color: var(--severity-high); }
@utility border-l-severity-medium { border-left-color: var(--severity-medium); }
@utility border-l-severity-low { border-left-color: var(--severity-low); }
```

- [ ] **Step 3: 验证 CSS 编译**

```bash
cd E:/code-reviewer/frontend && npx vite build --logLevel error
```

Expected: build 成功，无错误

- [ ] **Step 4: Commit**

```bash
cd E:/code-reviewer/frontend && git add vite.config.ts src/index.css && git commit -m "feat: configure Tailwind CSS v4 + shadcn/ui dual theme CSS variables"
```

---

### Task 3: 安装 shadcn/ui 组件 + 创建 ThemeProvider

**Files:**
- Create: `frontend/src/components/theme-provider.tsx`
- Create: `frontend/src/hooks/use-theme.ts`
- Modify: `frontend/src/main.tsx`
- 运行 `npx shadcn@latest add` 创建以下组件文件：
  - `frontend/src/components/ui/button.tsx`
  - `frontend/src/components/ui/badge.tsx`
  - `frontend/src/components/ui/card.tsx`
  - `frontend/src/components/ui/separator.tsx`
  - `frontend/src/components/ui/skeleton.tsx`
  - `frontend/src/components/ui/collapsible.tsx`

**Interfaces:**
- Consumes: Task 2 的 Tailwind 主题 CSS 变量
- Produces: shadcn/ui 组件 + `useTheme()` hook + ThemeProvider

- [ ] **Step 1: 安装所需的 shadcn/ui 组件**

```bash
cd E:/code-reviewer/frontend && npx shadcn@latest add button badge card separator skeleton collapsible --overwrite
```

Expected: 在 `src/components/ui/` 下生成各组件文件，覆盖已存在的（如果有）

- [ ] **Step 2: 创建 `src/hooks/use-theme.ts`**

```typescript
import { useEffect, useState } from "react";

type Theme = "dark" | "light" | "system";

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "system";
    return (localStorage.getItem("theme") as Theme) || "system";
  });

  const resolvedTheme = (() => {
    if (theme === "system") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    return theme;
  })();

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(resolvedTheme);
  }, [resolvedTheme]);

  useEffect(() => {
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      const handler = () => {
        const root = document.documentElement;
        root.classList.remove("light", "dark");
        root.classList.add(mq.matches ? "dark" : "light");
      };
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    }
  }, [theme]);

  const setTheme = (t: Theme) => {
    localStorage.setItem("theme", t);
    setThemeState(t);
  };

  return { theme, resolvedTheme, setTheme } as const;
}
```

- [ ] **Step 3: 创建 `src/components/theme-provider.tsx`**

```typescript
import { createContext, useContext } from "react";
import { useTheme } from "../hooks/use-theme";

type ThemeContextType = ReturnType<typeof useTheme>;

const ThemeContext = createContext<ThemeContextType | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const value = useTheme();
  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useThemeContext() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useThemeContext must be used within ThemeProvider");
  return ctx;
}
```

- [ ] **Step 4: 修改 `src/main.tsx` — 引入 ThemeProvider**

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import { ThemeProvider } from "./components/theme-provider";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);
```

注意：保持 `./App.tsx` 的 import 不变（`allowImportingTsExtensions` 已启用）

- [ ] **Step 5: 验证编译**

```bash
cd E:/code-reviewer/frontend ; npx tsc -b --noEmit 2>&1 | Select-Object -First 20
```

Expected: 无类型错误

- [ ] **Step 6: Commit**

```bash
cd E:/code-reviewer/frontend && git add src/components/ui/ src/components/theme-provider.tsx src/hooks/use-theme.ts src/main.tsx && git commit -m "feat: add shadcn/ui components + ThemeProvider with dark/light/system toggle"
```

---

### Task 4: 创建 FindingCard 组件 + 严重度工具函数

**Files:**
- Create: `frontend/src/components/FindingCard.tsx`
- Create: `frontend/src/lib/severity.tsx`

**Interfaces:**
- Consumes: `Finding` 类型（`src/types/index.ts`），shadcn/ui Badge + Button + Collapsible（Task 3）
- Produces: `<FindingCard finding={f} />` 组件 + `severityConfig` 映射表

```typescript
// FindingCard
interface FindingCardProps {
  finding: Finding;
  defaultOpen?: boolean;
}
```

```typescript
// severity.tsx 导出
interface SeverityConfig {
  label: string;
  badgeClass: string;
  borderClass: string;
  Icon: React.ComponentType<{ className?: string }>;
}
const severityConfig: Record<string, SeverityConfig>;
```

- [ ] **Step 1: 创建 `src/lib/severity.tsx`**

```typescript
import {
  CircleAlert,
  TriangleAlert,
  AlertTriangle,
  Info,
  type LucideIcon,
} from "lucide-react";

export interface SeverityConfig {
  label: string;
  badgeVariant: "critical" | "high" | "medium" | "low";
  borderColor: string;
  icon: LucideIcon;
}

export const severityConfigMap: Record<string, SeverityConfig> = {
  critical: {
    label: "严重",
    badgeVariant: "critical",
    borderColor: "border-l-severity-critical",
    icon: CircleAlert,
  },
  high: {
    label: "高危",
    badgeVariant: "high",
    borderColor: "border-l-severity-high",
    icon: TriangleAlert,
  },
  medium: {
    label: "中危",
    badgeVariant: "medium",
    borderColor: "border-l-severity-medium",
    icon: AlertTriangle,
  },
  low: {
    label: "低危",
    badgeVariant: "low",
    borderColor: "border-l-severity-low",
    icon: Info,
  },
};

export function getSeverityConfig(severity: string): SeverityConfig {
  return severityConfigMap[severity] ?? severityConfigMap.low;
}
```

- [ ] **Step 2: 确认 Badge 组件的 variant 支持自定义严重度**

Read `frontend/src/components/ui/badge.tsx`，默认的 shadcn Badge 有 `default | secondary | destructive | outline`，需要扩展支持自定义 variant。修改 badge.tsx：

```typescript
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
        critical:
          "border-transparent bg-severity-critical/15 text-severity-critical",
        high:
          "border-transparent bg-severity-high/15 text-severity-high",
        medium:
          "border-transparent bg-severity-medium/15 text-severity-medium",
        low:
          "border-transparent bg-severity-low/15 text-severity-low",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
```

- [ ] **Step 3: 创建 `src/components/FindingCard.tsx`**

```typescript
import { useState } from "react";
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

export default function FindingCard({ finding, defaultOpen = false }: FindingCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const config = getSeverityConfig(finding.severity);
  const Icon = config.icon;

  return (
    <Card className={`border-l-[3px] ${config.borderColor} mb-2`}>
      <CardHeader className="p-3 pb-0">
        <div
          className="flex items-center justify-between cursor-pointer select-none"
          onClick={() => setOpen(!open)}
        >
          <div className="flex items-center gap-2 min-w-0">
            <Badge variant={config.badgeVariant}>
              <Icon className="h-3 w-3" />
              {config.label}
            </Badge>
            <span className="font-mono text-sm text-foreground/80 truncate">
              {finding.file}
              <span className="text-muted-foreground text-xs ml-1">
                :{finding.line}
              </span>
            </span>
            <span className="text-sm font-medium text-foreground truncate hidden sm:inline">
              — {finding.title}
            </span>
          </div>

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
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
            <ChevronDown
              className={`h-4 w-4 text-muted-foreground transition-transform duration-150 ${
                open ? "rotate-180" : ""
              }`}
            />
          </div>
        </div>
        {/* Show title below on mobile where it might be truncated above */}
        <p className="text-sm font-medium mt-1 sm:hidden">{finding.title}</p>
      </CardHeader>

      {open && (
        <CardContent className="p-3 pt-2 space-y-2">
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
```

- [ ] **Step 4: 验证编译**

```bash
cd E:/code-reviewer/frontend && npx tsc -b --noEmit 2>&1
```

Expected: 无类型错误（可能有未使用的 import 警告，修复它们）

- [ ] **Step 5: Commit**

```bash
cd E:/code-reviewer/frontend && git add src/components/FindingCard.tsx src/lib/severity.tsx src/components/ui/badge.tsx && git commit -m "feat: add FindingCard component with severity config"
```

---

### Task 5: 重写 ReviewProgress 组件

**Files:**
- Rewrite: `frontend/src/components/ReviewProgress.tsx`

**Interfaces:**
- Consumes: `ReviewLog` 类型, shadcn/ui Card + Button (Task 3)
- Produces: `<ReviewProgress logs={logs} logPolling={logPolling} />` 组件（接口不变）

```typescript
interface ReviewProgressProps {
  logs: ReviewLog[];
  logPolling: boolean;
}
```

- [ ] **Step 1: 重写 `src/components/ReviewProgress.tsx`**

```typescript
import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Loader2 } from "lucide-react";
import type { ReviewLog } from "../types";

const stepLabels: Record<string, string> = {
  load_pr: "获取代码变更",
  collect_context: "收集上下文",
  planning: "规划策略",
  run_reviews: "执行审查",
  reflection: "反思",
  generate_report: "生成报告",
  tool_call: "",
};

const MAX_VISIBLE = 50;

interface ReviewProgressProps {
  logs: ReviewLog[];
  logPolling: boolean;
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("zh-CN", { hour12: false });
}

export default function ReviewProgress({ logs, logPolling }: ReviewProgressProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const displayLogs = expanded ? logs : logs.slice(-MAX_VISIBLE);
  const hiddenCount = logs.length - MAX_VISIBLE;

  const isComplete = logs.length > 0 && logs[logs.length - 1].message === "审查完成";
  const isFailed = !logPolling && !isComplete && logs.length > 0;

  const statusColor = isComplete
    ? "text-severity-low"
    : isFailed
      ? "text-destructive"
      : "text-primary";

  return (
    <Card className="mb-6">
      <CardHeader className="pb-2">
        <CardTitle className={`flex items-center gap-2 text-base ${statusColor}`}>
          {logPolling && !isComplete && <Loader2 className="h-4 w-4 animate-spin" />}
          {isComplete ? "审查完成" : isFailed ? "审查失败" : "审查进行中"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="max-h-[400px] overflow-auto font-mono text-[13px] leading-[1.8]">
          {hiddenCount > 0 && !expanded && (
            <div className="mb-2">
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-muted-foreground"
                onClick={() => setExpanded(true)}
              >
                展开全部 {logs.length} 条
              </Button>
            </div>
          )}

          {displayLogs.map((log) => (
            <div
              key={log.id}
              className={log.step === "tool_call" ? "pl-6" : ""}
              style={{ color: log.level === "error" ? "hsl(var(--destructive))" : undefined }}
            >
              <span className="text-[11px] text-muted-foreground">
                {formatTime(log.created_at)}
              </span>{" "}
              {log.step !== "tool_call" && (
                <span className="font-semibold text-primary">
                  [{stepLabels[log.step] || log.step}]
                </span>
              )}{" "}
              {log.message}
            </div>
          ))}

          {logPolling && !isComplete && (
            <div className="text-primary mt-1 animate-pulse">...</div>
          )}

          {isComplete && (
            <div className="text-severity-low font-semibold mt-1">审查完成</div>
          )}

          {isFailed && (
            <div className="text-destructive font-semibold mt-1">审查失败</div>
          )}

          <div ref={bottomRef} />
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: 验证编译**

```bash
cd E:/code-reviewer/frontend && npx tsc -b --noEmit 2>&1
```

Expected: 无类型错误

- [ ] **Step 3: Commit**

```bash
cd E:/code-reviewer/frontend && git add src/components/ReviewProgress.tsx && git commit -m "refactor: rewrite ReviewProgress with shadcn/ui components"
```

---

### Task 6: 重写 ReviewDetail 页面

**Files:**
- Rewrite: `frontend/src/pages/ReviewDetail.tsx`

**Interfaces:**
- Consumes: `ReviewTask`, `ReviewReport`, `Finding`, `ReviewLog` 类型；`reviewApi`（`src/api/reviews.ts`）；`FindingCard`（Task 4）；`ReviewProgress`（Task 5）；shadcn/ui Badge + Button + Separator（Task 3）；lucide-react 图标；`getSeverityConfig`（Task 4）
- Produces: 完整的审查报告页面，路由 `/reviews/:id`

- [ ] **Step 1: 重写 `src/pages/ReviewDetail.tsx`**

```typescript
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ChevronLeft, TriangleAlert } from "lucide-react";
import type { Finding, ReviewLog, ReviewReport, ReviewTask } from "../types";
import { reviewApi } from "../api/reviews";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Separator } from "../components/ui/separator";
import { Skeleton } from "../components/ui/skeleton";
import FindingCard from "../components/FindingCard";
import ReviewProgress from "../components/ReviewProgress";
import { getSeverityConfig } from "../lib/severity";

const riskColors: Record<string, "critical" | "high" | "medium" | "low"> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

function groupFindingsBySeverity(findings: Finding[]) {
  const groups: Record<string, Finding[]> = {
    critical: [],
    high: [],
    medium: [],
    low: [],
  };
  findings.forEach((f) => groups[f.severity]?.push(f));
  return groups;
}

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<ReviewTask | null>(null);
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [polling, setPolling] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState<string | null>(null);
  const [logs, setLogs] = useState<ReviewLog[]>([]);
  const [logPolling, setLogPolling] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;

    const fetchAll = () => {
      reviewApi.status(id).then((r) => setTask(r.data));
      reviewApi.report(id).then((r) => {
        if (r.data.report) setReport(r.data.report);
        if (r.data.status !== "pending" && r.data.status !== "running") {
          setPolling(false);
        }
      });
      reviewApi.logs(id).then((r) => {
        setLogs(r.data);
        const hasComplete = r.data.some(
          (l: ReviewLog) =>
            l.message === "审查完成" ||
            (l.level === "error" && l.step === "generate_report")
        );
        if (hasComplete) setLogPolling(false);
      });
    };

    fetchAll();
    setLoading(false);
    const interval = setInterval(fetchAll, 2000);
    return () => clearInterval(interval);
  }, [id]);

  // ── Loading state ──
  if (loading && polling) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // ── Still polling, no report yet ──
  if (!report && polling) {
    return <ReviewProgress logs={logs} logPolling={logPolling} />;
  }

  // ── Failed state ──
  if (!report && !polling && task?.status === "failed") {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-6">
          <h2 className="text-lg font-semibold text-destructive flex items-center gap-2">
            <TriangleAlert className="h-5 w-5" />
            审查失败
          </h2>
          <p className="text-destructive/80 mt-2">
            {task.error_message || "未知错误"}
          </p>
        </div>
      </div>
    );
  }

  // ── No report, not polling, not failed ──
  if (!report && !polling && task?.status !== "failed") {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          返回
        </Button>
        <div className="rounded-lg border p-6 text-center text-muted-foreground">
          未找到报告
        </div>
      </div>
    );
  }

  if (!report) return null;

  const grouped = groupFindingsBySeverity(report.findings);
  const severityEntries = Object.entries(grouped).filter(([, f]) => f.length > 0);
  const riskConfig = getSeverityConfig(report.risk_level);
  const RiskIcon = riskConfig.icon;

  const allFindings = report.findings;
  const filteredFindings = filterSeverity
    ? allFindings.filter((f) => f.severity === filterSeverity)
    : allFindings;

  // Group filtered findings by severity
  const filteredGrouped = groupFindingsBySeverity(filteredFindings);
  const filteredEntries = Object.entries(filteredGrouped).filter(([, f]) => f.length > 0);

  return (
    <div className="space-y-4">
      {/* Navigation */}
      <Button variant="ghost" onClick={() => navigate(-1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        返回
      </Button>

      {/* Progress log (if not polling) */}
      {report && logs.length > 0 && !polling && (
        <ReviewProgress logs={logs} logPolling={false} />
      )}

      {/* Risk level header */}
      <div className="flex items-center gap-3">
        <Badge variant={riskColors[report.risk_level]}>
          <RiskIcon className="h-3.5 w-3.5" />
          {report.risk_level.toUpperCase()}
        </Badge>
        <span className="text-sm">{report.summary}</span>
      </div>

      <Separator />

      {/* Stats row */}
      <div className="grid grid-cols-5 gap-3">
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold">{report.stats.total_findings}</div>
          <div className="text-xs text-muted-foreground mt-1">总问题</div>
        </div>
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold">{report.stats.impacted_files}</div>
          <div className="text-xs text-muted-foreground mt-1">涉及文件</div>
        </div>
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold text-severity-critical">
            {report.stats.by_severity.critical || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">严重</div>
        </div>
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold text-severity-high">
            {report.stats.by_severity.high || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">高危</div>
        </div>
        <div className="rounded-lg border bg-card p-4 text-center">
          <div className="text-2xl font-bold text-severity-medium">
            {report.stats.by_severity.medium || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">中危</div>
        </div>
      </div>

      {/* Severity filter pills */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setFilterSeverity(null)}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
            filterSeverity === null
              ? "border-primary bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:text-foreground"
          }`}
        >
          全部 ({report.findings.length})
        </button>
        {severityEntries.map(([severity, findings]) => {
          const cfg = getSeverityConfig(severity);
          const Icon = cfg.icon;
          const active = filterSeverity === severity;
          return (
            <button
              key={severity}
              onClick={() =>
                setFilterSeverity(active ? null : severity)
              }
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                active
                  ? "border-severity-" + severity + " bg-severity-" + severity + "/10 text-severity-" + severity
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {cfg.label} ({findings.length})
            </button>
          );
        })}
      </div>

      {/* Findings list */}
      {filteredEntries.length === 0 ? (
        <div className="rounded-lg border p-8 text-center text-muted-foreground">
          该严重度下无发现问题
        </div>
      ) : (
        filteredEntries.map(([severity, findings]) => (
          <div key={severity} className="space-y-2">
            {findings.map((f, i) => (
              <FindingCard
                key={`${f.file}-${f.line}-${i}`}
                finding={f}
                defaultOpen={severity === "critical" || severity === "high"}
              />
            ))}
          </div>
        ))
      )}
    </div>
  );
}
```

- [ ] **Step 2: 验证编译**

```bash
cd E:/code-reviewer/frontend && npx tsc -b --noEmit 2>&1
```

Expected: 无类型错误。如有，修复后再 commit。

- [ ] **Step 3: Commit**

```bash
cd E:/code-reviewer/frontend && git add src/pages/ReviewDetail.tsx && git commit -m "refactor: rewrite ReviewDetail with shadcn/ui components"
```

---

### Task 7: 添加风险分布迷你柱状图

**Files:**
- Modify: `frontend/src/pages/ReviewDetail.tsx`

**Interfaces:**
- Consumes: `ReviewReport.stats.by_severity`（Record<string, number>），Recharts 库
- Produces: 页面中 stats 行下方嵌入水平堆叠条 + 图例

- [ ] **Step 1: 在 ReviewDetail.tsx 的 stats 行下方插入图表区**

在 ReviewDetail.tsx 末尾 `</div>`（最外层容器闭合标签）之前，stats 行之后，severity filter pills 之前插入：

```typescript
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
```

然后插入 JSX（放在 `</div>` stats grid 之后，severity filters 之前）：

```tsx
{/* Risk distribution chart */}
<div className="rounded-lg border bg-card p-4">
  <h3 className="text-sm font-medium mb-3">风险分布</h3>
  <ResponsiveContainer width="100%" height={180}>
    <BarChart
      data={[
        {
          name: "问题数",
          critical: report.stats.by_severity.critical || 0,
          high: report.stats.by_severity.high || 0,
          medium: report.stats.by_severity.medium || 0,
          low: report.stats.by_severity.low || 0,
        },
      ]}
      layout="vertical"
      margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
    >
      <XAxis type="number" hide />
      <YAxis type="category" dataKey="name" hide />
      <Tooltip
        contentStyle={{
          backgroundColor: "hsl(var(--card))",
          border: "1px solid hsl(var(--border))",
          borderRadius: "6px",
          fontSize: "13px",
        }}
        labelStyle={{ color: "hsl(var(--foreground))" }}
      />
      <Bar
        dataKey="critical"
        stackId="a"
        fill="hsl(var(--severity-critical))"
        radius={[0, 0, 0, 0]}
      />
      <Bar
        dataKey="high"
        stackId="a"
        fill="hsl(var(--severity-high))"
      />
      <Bar
        dataKey="medium"
        stackId="a"
        fill="hsl(var(--severity-medium))"
      />
      <Bar
        dataKey="low"
        stackId="a"
        fill="hsl(var(--severity-low))"
        radius={[4, 4, 4, 4]}
      />
    </BarChart>
  </ResponsiveContainer>
  {/* Chart legend */}
  <div className="flex flex-wrap gap-4 mt-2 text-xs text-muted-foreground">
    <span className="flex items-center gap-1.5">
      <span className="w-3 h-3 rounded-sm bg-severity-critical" />
      严重: {report.stats.by_severity.critical || 0}
    </span>
    <span className="flex items-center gap-1.5">
      <span className="w-3 h-3 rounded-sm bg-severity-high" />
      高危: {report.stats.by_severity.high || 0}
    </span>
    <span className="flex items-center gap-1.5">
      <span className="w-3 h-3 rounded-sm bg-severity-medium" />
      中危: {report.stats.by_severity.medium || 0}
    </span>
    <span className="flex items-center gap-1.5">
      <span className="w-3 h-3 rounded-sm bg-severity-low" />
      低危: {report.stats.by_severity.low || 0}
    </span>
  </div>
</div>
```

- [ ] **Step 2: 确认 `bg-severity-*` utility classes 在 CSS 中有定义**

检查 `src/index.css`，确保 severity 背景色作为 utility 或 component 类存在。如果没有，在 `index.css` 中添加：

```css
@layer utilities {
  .bg-severity-critical { background-color: var(--severity-critical); }
  .bg-severity-high { background-color: var(--severity-high); }
  .bg-severity-medium { background-color: var(--severity-medium); }
  .bg-severity-low { background-color: var(--severity-low); }
}
```

- [ ] **Step 3: 验证编译**

```bash
cd E:/code-reviewer/frontend ; npx tsc -b --noEmit 2>&1 | Select-Object -First 20
```

Expected: 无类型错误

- [ ] **Step 4: Commit**

```bash
cd E:/code-reviewer/frontend && git add src/pages/ReviewDetail.tsx src/index.css && git commit -m "feat: add risk distribution stacked bar chart with Recharts"
```

---

### Task 8: 端到端验证 + 微调

**Files:**
- 验证所有修改文件的 import 一致性

**Interfaces:**
- Consumes: 所有 Task 1-6 的产出
- Produces: 可运行的 dev server，ReviewDetail 页面正常工作

- [ ] **Step 1: 运行 TypeScript 检查**

```bash
cd E:/code-reviewer/frontend && npx tsc -b --noEmit 2>&1
```

Expected: 零错误。如有 error 修复它们。

- [ ] **Step 2: 运行 build**

```bash
cd E:/code-reviewer/frontend && npm run build 2>&1
```

Expected: build 成功，无错误

- [ ] **Step 3: 启动 dev server 验证页面渲染**

```bash
cd E:/code-reviewer/frontend && npm run dev
```

手动检查：
- 访问 `/reviews/<有效ID>` 确认 ReviewDetail 正常渲染
- 确认严重度 Badge 使用 lucide-react 图标（非 emoji）
- 确认 Finding 卡片可折叠展开
- 确认返回按钮可用
- 确认 loading skeleton 显示正常
- 确认黑暗模式切换 `.dark` class 生效

- [ ] **Step 4: Commit（如有修复）**

```bash
cd E:/code-reviewer/frontend && git add -A && git commit -m "fix: type errors and import consistency after shadcn/ui migration"
```
