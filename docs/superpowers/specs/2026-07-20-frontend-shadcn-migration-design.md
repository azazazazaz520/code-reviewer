# Code Reviewer 前端 shadcn/ui 重设计规范

## 概述

将前端从 Ant Design 6 迁移到 shadcn/ui（Radix UI + Tailwind CSS），分阶段渐进式替换。首阶段重写 ReviewDetail 页面，后续逐步覆盖其余页面。

## 设计系统

### 色板（Developer Tool / IDE）

基于 CSS Variables，支持 `.dark` / `:root` 双主题：

| Token | Light | Dark |
|-------|-------|------|
| `--background` | `0 0% 100%` | `222.2 84% 4.9%` |
| `--foreground` | `222.2 84% 4.9%` | `210 40% 98%` |
| `--card` | `0 0% 100%` | `217.2 32.6% 17.5%` |
| `--card-foreground` | `222.2 84% 4.9%` | `210 40% 98%` |
| `--primary` | `142.1 76.2% 36.3%` | `142.1 76.2% 36.3%` |
| `--primary-foreground` | `355.7 100% 97.3%` | `355.7 100% 97.3%` |
| `--secondary` | `210 40% 96.1%` | `217.2 32.6% 17.5%` |
| `--muted` | `210 40% 96.1%` | `217.2 32.6% 12.5%` |
| `--muted-foreground` | `215.4 16.3% 46.9%` | `215 20.2% 65.1%` |
| `--border` | `214.3 31.8% 91.4%` | `217.2 32.6% 25.5%` |
| `--destructive` | `0 72.2% 50.6%` | `0 72.2% 50.6%` |
| `--ring` | `142.1 76.2% 36.3%` | `142.1 76.2% 36.3%` |

### 严重度色彩语义

| 级别 | 色相 | Badge 类名 |
|------|------|-----------|
| Critical | Red (0 72.2% 50.6%) | `badge-critical` |
| High | Orange (25 95% 50%) | `badge-high` |
| Medium | Amber (43 74% 45%) | `badge-medium` |
| Low | Green (142.1 70% 30%) | `badge-low` |

### 字体

使用 Tailwind 内置字体栈（Inter / Geist），等宽部分用 `font-mono`。

### 图标

统一使用 `lucide-react`。**禁止 emoji 作为结构性图标。**

| 用途 | 图标 |
|------|------|
| 仪表盘 | `LayoutDashboard` |
| 仓库管理 | `Github` (或 `GitBranch`) |
| 发起审查 | `Plus` |
| 严重 | `CircleAlert` |
| 高危 | `TriangleAlert` |
| 中危 | `AlertTriangle` |
| 低危 | `Info` |
| 复制 | `Copy` |
| 返回 | `ChevronLeft` |
| 暗色/亮色切换 | `Moon` / `Sun` |
| 搜索 | `Search` |

## 页面设计规范

### Phase 1：ReviewDetail（审查报告）

**导航**：返回按钮（`router.go(-1)`）+ 页面标题 + 风险 Badge

**顶部信息栏**：
- 风险等级 Badge（图标 + 文字 + 颜色，三重编码，不依赖颜色单独传达信息）
- 一句话总结文案
- PR 元信息行（PR 编号 · commit 标题 · 分支 · 时间）

**概览统计**：5 列数字卡片（总问题 / 涉及文件 / 严重 / 高危 / 中危），数字带对应严重度颜色

**严重度过滤**：横向 pill 标签组，`全部 (N)` + 各严重度计数，点击切换过滤

**Finding 卡片**（替代 Collapse）：
- 左侧色条（3px solid 严重度色）
- 标题行：严重度 Badge + 文件路径 `:行号` + 复制按钮
- 可折叠详情区（初始展开第一张，其余折叠）：
  - 原因段落
  - 建议区（带左边框高亮，monospace 字体）
- 每张卡片点击标题行折叠/展开详情

**进度日志区**（ReviewProgress）：
- 审查进行中时显示时间线日志
- 完成后折叠或移除

### Phase 2：Dashboard（仪表盘）

- 统计卡片行：总审查 / 本月审查 / 活跃仓库
- 热力图：GitHub 风格，带色阶图例
- 最近审查表格
- 风险分布：迷你柱状图（Recharts）

### Phase 3：RepoList / RepoDetail

- CRUD 表格用 shadcn/ui DataTable
- 表单用 shadcn/ui Form + Input
- Modal 用 shadcn/ui Dialog

### Phase 4：Layout

- 侧边栏导航（shadcn/ui 风格）
- 主题切换开关
- 响应式适配

## 交互规范

- 所有可点击元素提供 `cursor-pointer` + hover 过渡（150ms）
- Loading 状态使用 Skeleton 而非空白等待
- 空状态给出引导文案和操作按钮
- 严重度信息三重编码（图标 + 颜色 + 文字标签），不依赖颜色单独传达
- 热力图每个单元格提供 Tooltip（精确数值）
- 支持 `prefers-reduced-motion`

## 技术栈

| 项 | 值 |
|----|-----|
| 框架 | React 19 |
| 构建 | Vite 8 |
| 类型 | TypeScript 6 |
| 样式 | Tailwind CSS 4 |
| 组件 | shadcn/ui (Radix UI primitives) |
| 图标 | lucide-react |
| 图表 | Recharts |
| 路由 | react-router-dom 7 |

## 迁移阶段

| Phase | 范围 | 产出 |
|-------|------|------|
| 1 | 项目初始化 + ReviewDetail 页面 | Tailwind + shadcn/ui 配置 + 重写 ReviewDetail |
| 2 | Dashboard 页面 | 统计卡片 + 热力图 + 表格 |
| 3 | RepoList + RepoDetail 页面 | CRUD 表格 + 表单 |
| 4 | Layout + 全局 | 侧边栏 + 主题切换 |
| 5 | 清理 | 移除 antd 依赖 |
