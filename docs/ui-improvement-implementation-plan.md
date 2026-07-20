# UI 改进实施文档

日期：2026-07-21

## 背景

当前前端已经具备不错的基础：使用 Tailwind CSS、shadcn/ui 风格组件、主题 token、深色模式、Skeleton 加载态，以及围绕代码审查场景建立的风险等级色彩。下一步的重点不是重做视觉风格，而是补齐响应式布局、可访问交互、信息层级和关键工作流体验，让这个代码审查工具更像一个可以长期高频使用的专业控制台。

## 目标

1. 提升 Dashboard、仓库详情、审查详情等核心页面在桌面和移动端的可用性。
2. 让风险、发现项、审查进度和操作入口更容易扫描、过滤和执行。
3. 将自定义弹窗、可点击 div、原生表单控件逐步收敛到可访问的组件模式。
4. 保持现有设计 token 和深色模式能力，避免引入一套割裂的新视觉体系。

## 非目标

1. 不在本阶段重构业务数据结构或后端 API。
2. 不引入新的大型 UI 框架。
3. 不把工具型控制台改造成营销型首页或装饰性页面。
4. 不一次性替换所有组件，优先处理会影响核心工作流的界面。

## 现状观察

核心页面集中在 `frontend/src/pages`，通用布局和交互组件集中在 `frontend/src/components`。目前主要问题包括：

1. 多处使用固定列数布局，例如 Dashboard 的 `grid-cols-3`、审查详情页的 `grid-cols-5`，在窄屏下容易拥挤。
2. 表格缺少统一的横向滚动容器或移动端替代形态，仓库列表、审查历史、发现项数据在小屏上阅读压力较大。
3. 侧边栏在桌面端可折叠，但缺少真正的移动端抽屉导航。
4. 若干交互元素使用可点击 `div`，键盘操作、ARIA 状态和焦点反馈不足。
5. 弹窗为手写 overlay，缺少标准 dialog 的焦点管理、Escape 关闭、标题关联和无障碍语义。
6. Dashboard 的指标卡、风险分布和热力图信息较分散，缺少一眼判断风险趋势的主视觉层级。

## 实施阶段

### 阶段 1：响应式基础与页面骨架

优先文件：

- `frontend/src/components/Layout.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/RepoList.tsx`
- `frontend/src/pages/RepoDetail.tsx`
- `frontend/src/pages/ReviewDetail.tsx`

实施内容：

1. 将固定栅格改为响应式栅格，例如 `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`，审查详情的五项指标可改为 `grid-cols-2 md:grid-cols-3 xl:grid-cols-5`。
2. 页面容器统一为更弹性的结构，例如 `mx-auto w-full max-w-7xl p-4 sm:p-6`，减少大屏空旷和小屏压迫。
3. 表格外层增加 `overflow-x-auto`，并统一最小宽度，保证移动端不会挤压列内容。
4. 侧边栏增加移动端抽屉或覆盖层导航；桌面端保留现有折叠能力。
5. 导航激活态从严格路径匹配改为支持详情页前缀匹配，例如仓库详情仍能高亮仓库入口。

验收标准：

1. Dashboard、仓库列表、仓库详情、审查详情在 375px、768px、1440px 宽度下无明显内容溢出。
2. 所有表格在窄屏下可以横向滚动，列内容不互相覆盖。
3. 移动端可以打开、关闭导航，并且页面主内容不被侧边栏遮挡。

### 阶段 2：核心信息层级优化

优先文件：

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/components/ReviewHeatmap.tsx`
- `frontend/src/pages/ReviewDetail.tsx`
- `frontend/src/components/FindingCard.tsx`

实施内容：

1. Dashboard 顶部增加更明确的主摘要区，突出当前总体风险、待处理高危发现、最近审查状态。
2. 指标卡增加图标、趋势或辅助说明，避免只有孤立数字。
3. 风险分布和热力图增加筛选上下文，例如时间范围、仓库过滤、总量说明。
4. 审查详情页顶部加入仓库、PR、commit、开始时间、耗时、状态等元信息，让用户先建立上下文。
5. 审查详情页增加醒目的风险摘要 banner，用 severity token 表达状态，但不要只依赖颜色。
6. 发现项列表支持按 severity 筛选；Critical 和 High 可默认优先展开第一个。
7. 发现项卡片中建议内容使用代码块或结构化区域展示，增加复制、跳转文件行、标记处理等动作入口。

验收标准：

1. 用户打开 Dashboard 后，3 秒内能判断系统风险是否值得立刻处理。
2. 用户打开审查详情后，不需要滚动即可看到审查对象、风险等级和关键统计。
3. 发现项按严重程度浏览和定位时，操作路径不超过两步。

### 阶段 3：可访问交互与组件收敛

优先文件：

- `frontend/src/components/FindingCard.tsx`
- `frontend/src/components/ReviewHeatmap.tsx`
- `frontend/src/components/ReviewProgress.tsx`
- `frontend/src/components/SubmitReviewModal.tsx`
- `frontend/src/pages/RepoList.tsx`

实施内容：

1. 将可点击 `div` 替换为语义化 `button` 或 shadcn/ui 组件。
2. 折叠区域补齐 `aria-expanded`、`aria-controls` 和键盘 Enter/Space 操作。
3. 热力图单元格使用 button，补齐 `aria-label`，说明日期、审查数量和风险信息。
4. 手写弹窗迁移到 Dialog 组件，补齐 `role="dialog"`、`aria-modal`、`aria-labelledby`、焦点 trap、Escape 关闭和关闭后焦点恢复。
5. 表单控件统一使用 Label、Input、Select、Textarea、Alert 等组件，减少原生控件和自定义样式混用。
6. 复制、删除、提交失败等操作增加 toast 或明确反馈，避免静默失败。

验收标准：

1. 仅使用键盘即可完成打开弹窗、选择 PR/commit、提交审查、展开发现项、复制建议等主要操作。
2. 弹窗打开后焦点进入弹窗，关闭后回到触发按钮。
3. 交互控件在 hover、focus-visible、disabled、loading 状态下都有清晰反馈。

### 阶段 4：视觉一致性与设计 token

优先文件：

- `frontend/src/index.css`
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/card.tsx`
- 其他新增或调整的 shadcn/ui 组件

实施内容：

1. 保留现有主题 token，并明确 primary、severity、muted、border、ring 的职责，避免主按钮颜色和风险颜色互相抢语义。
2. 检查中风险黄色、低风险绿色、深色模式下的对比度，保证文本和图标可读。
3. 统一 Card 的密度、标题字号、间距和边框，控制台内的卡片保持克制，不嵌套卡片。
4. 对危险操作使用 destructive variant，并结合图标和文字，不只依赖颜色。
5. 图表和热力图增加图例、总量和空态，降低用户猜测成本。

验收标准：

1. 浅色和深色模式下，核心文本、按钮、风险标签均满足可读性要求。
2. 同一类型操作在不同页面中使用一致的颜色、大小和状态样式。
3. 新增组件优先复用现有 token 和 shadcn/ui 组件。

## 建议实施顺序

1. 先做响应式基础：布局、表格滚动、页面容器、移动端导航。
2. 再做可访问交互：Dialog、button 语义、键盘操作、ARIA 状态。
3. 然后优化 Dashboard 和 Review Detail 的信息层级。
4. 最后统一颜色 token、图表图例、空态和操作反馈。

这个顺序能先解决最容易暴露的可用性问题，再逐步提升专业感和效率。实施时建议每个阶段单独提交，避免把布局、语义和视觉调整揉成一个难以审查的大改动。

## 实施记录

### 2026-07-21 首批改造

已完成：

1. 全局 Layout 增加移动端顶部栏和抽屉式导航，桌面端保留可折叠侧边栏。
2. 页面主容器调整为响应式宽度和间距。
3. Dashboard、RepoList、RepoDetail 的固定栅格和表格改为移动优先布局，表格统一使用已有 Table 组件的横向滚动容器。
4. ReviewDetail 的统计卡片改为响应式栅格，并将风险摘要提升为更醒目的 banner。
5. FindingCard、ReviewHeatmap、ReviewProgress 的主要点击区域改为语义化 button，并补充焦点样式、`aria-expanded`、`aria-controls` 或 `aria-label`。

验证：

1. `npm.cmd run build` 通过。
2. `npm.cmd run lint` 通过。

待继续：

1. 将 SubmitReviewModal 和 RepoList 添加/编辑仓库 overlay 迁移到 Dialog 或等价的可访问弹窗组件。
2. 表单控件继续收敛到 Label/Input/Select 等组件模式。
3. 增加提交、复制、保存失败等操作反馈。
4. 继续优化 Dashboard 与 ReviewDetail 的筛选、空态和图表说明。

## 验证清单

1. 在 375px、768px、1440px 三个宽度手动检查核心页面。
2. 使用键盘 Tab、Enter、Space、Escape 走完主要操作流。
3. 检查浅色和深色模式下的风险标签、按钮、表格和弹窗。
4. 检查空数据、加载中、错误、提交中、删除确认等状态。
5. 运行前端 lint、类型检查和现有测试。

## 后续可拆分任务

1. 改造全局 Layout 与移动端导航。
2. 统一表格响应式容器和空态。
3. 将 SubmitReviewModal 迁移到 Dialog + shadcn 表单组件。
4. 改造 FindingCard 和 ReviewHeatmap 的可访问交互。
5. 优化 Dashboard 信息层级和风险摘要。
6. 优化 ReviewDetail 的摘要、筛选和发现项操作。
7. 做一次主题 token、深色模式和对比度检查。
