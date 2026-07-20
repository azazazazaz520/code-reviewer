# UX 重设计：仪表盘 & 发起审查 & 报告页

日期：2026-07-20
状态：已确认

---

## 1. 背景与问题

### 1.1 仪表盘信息混乱

- **"风险"列**（最近审查表格）：显示的是 `ReviewTask.status`（pending/running/done/failed），和代码风险无关。用户期望看到审查结果的风险等级。
- **"平均风险"卡片**：后端逻辑是遍历所有报告取最严重的 `risk_level`（有关键字取 critical，否则 high，否则 medium，否则 low），这既不是平均值，也没有决策参考价值。
- **"标识"列**：`pr_number` 直接裸显示数字，缺少 `#` 前缀；commit hash 未截断，过长。

### 1.2 发起审查路径冗长

当前路径：仪表盘 → 仓库列表 → 仓库详情 → 选类型 + 手输 PR 号/Commit Hash → 提交（4 步，无辅助选择）。

用户需要离开工具去 GitHub 复制 PR 号，或去终端执行 `git log` 查 commit hash。

### 1.3 审查报告页可改进

- Findings 列表缺少快速过滤（按严重度筛选）
- Finding 卡片无复制功能，不方便贴到 GitHub/IDE

---

## 2. 设计方案

### 2.1 仪表盘重设计

#### 2.1.1 统计卡片行

- **保留**：总审查次数、本月审查、活跃仓库
- **删除**：平均风险
- 三卡片一行，每卡 `span={8}`（原为 `span={6}` 四列）

#### 2.1.2 审查活动热力图

横轴 × 纵轴 × 颜色 = 月份 × 仓库 × 最高风险等级。

**为什么用月份而不是天**：代码审查不是每天发生，日历热力图会大面积空白；按月聚合才有可读的信号。

**颜色编码**：

| 颜色 | 含义 | 条件 |
|------|------|------|
| 灰 `#f0f0f0` | 无审查 | 该月该仓库无已完成审查 |
| 绿 `#52c41a` | 低风险 | 该月最高风险为 low |
| 金 `#faad14` | 中风险 | 该月最高风险为 medium |
| 橙 `#fa8c16` | 高风险 | 该月最高风险为 high |
| 红 `#ff4d4f` | 严重 | 该月最高风险为 critical |

**交互**：hover 显示 tooltip（仓库名 + 月份 + 审查次数 + 最高风险等级）；点击某格跳转到该仓库详情页过滤到对应月份。

**后端 API**：新增 `GET /api/stats/heatmap`，返回结构：

```json
{
  "months": ["2026-01", "2026-02", ...],
  "repos": [
    {
      "repo_id": "xxx",
      "repo_name": "my-repo",
      "cells": [
        {"month": "2026-01", "review_count": 3, "worst_risk": "high"},
        {"month": "2026-02", "review_count": 0, "worst_risk": null},
        ...
      ]
    }
  ]
}
```

查询逻辑：`review_tasks JOIN review_reports`，按 `repo_id` + `strftime('%Y-%m', completed_at)` 分组，取该组中 `risk_level` 的最差值。

#### 2.1.3 最近审查表格

| 列 | 改动 |
|----|------|
| 仓库 | 不变 |
| 类型 | 不变（PR / Local） |
| ~~标识~~ → **目标** | PR 审查显示 `#42`；Local 审查显示 commit hash 前 7 位（如 `a1b2c3d`）；无标识显示 `—` |
| ~~风险(状态)~~ → **风险** | 改为显示 `risk_level`，用对应颜色 Tag（绿/金/橙/红）。需要 JOIN `review_reports` 获取 risk_level；无报告的 pending/running 任务显示"进行中"蓝色 Tag。 |
| 时间 | 不变 |
| 操作 | 不变 |

**后端改动**：`GET /api/stats/overview` 的 `recent_reviews` 需要附带 `risk_level`。扩展 `ReviewTaskResponse` 或新建带 risk 的响应模型。

#### 2.1.4 风险分布

保留现有的 Tag 列表。考虑把已完成 vs 进行中的审查数据分开显示。

---

### 2.2 发起审查流程改进

#### 2.2.1 入口

在**仪表盘**和**仓库列表页**各加一个醒目的"发起审查"按钮（`type="primary"`）。

#### 2.2.2 弹窗组件

新组件 `SubmitReviewModal`：

```
┌──────────────────────────────────────────────┐
│  发起审查                               [X]  │
│                                              │
│  仓库  [下拉选择，支持搜索]                    │
│                                              │
│  审查类型  ○ PR 审查   ○ Local Commit         │
│                                              │
│  ┌─ 选择目标 ─────────────────────────────┐  │
│  │ (PR 模式)                              │  │
│  │  ┌──────────────────────────────────┐  │  │
│  │  │ #42 fix: login bug     2h ago   │  │  │
│  │  │ #41 feat: dashboard    1d ago   │  │  │
│  │  └──────────────────────────────────┘  │  │
│  │                                        │  │
│  │ (Local 模式)                            │  │
│  │  ┌──────────────────────────────────┐  │  │
│  │  │ a1b2c3d feat: add login         │  │  │
│  │  │ e4f5g6h fix: null pointer       │  │  │
│  │  │ i7j8k9l chore: update deps      │  │  │
│  │  └──────────────────────────────────┘  │  │
│  └────────────────────────────────────────┘  │
│                                              │
│                     [取消]   [开始审查]       │
└──────────────────────────────────────────────┘
```

**交互逻辑**：
1. 用户从下拉选择仓库 → 触发加载 PR 列表或 commit 列表
2. 切换审查类型 → 切换列表内容
3. 列表每一项可点击选中，高亮显示
4. 点击"开始审查" → 调 `POST /api/repos/{repo_id}/reviews` → 关闭弹窗 → 跳转到审查详情页（轮询等待结果）

#### 2.2.3 后端新增 API

**`GET /api/repos/{repo_id}/prs`**

调用 GitHub API `GET /repos/{owner}/{repo}/pulls?state=open&per_page=20`。
返回：

```json
[
  {
    "number": 42,
    "title": "fix: login bug",
    "author": "alice",
    "branch": "fix/login-bug",
    "created_at": "2026-07-19T10:00:00Z"
  }
]
```

**`GET /api/repos/{repo_id}/commits?limit=20`**

在仓库本地路径执行 `git log --oneline -20 --format="%H %s %an %aI"`。
返回：

```json
[
  {
    "hash": "a1b2c3d4e5f6...",
    "short_hash": "a1b2c3d",
    "message": "feat: add login",
    "author": "alice",
    "date": "2026-07-19T10:00:00Z"
  }
]
```

**`POST /api/repos/{repo_id}/reviews`** — 现有接口，无需改动。弹窗提交的 payload 与当前 form 一致。

#### 2.2.4 仓库详情页

保留现有表单作为备选（用户可能已经习惯），但增加从 PR/commit 列表选择的支持——与 Modal 共享同一套列表组件。

---

### 2.3 审查报告页改进

#### 2.3.1 问题速览过滤条

在 summary 卡片下方、findings 列表上方，加一行可点击的过滤标签：

```
🔴 严重 (2)  🟠 高危 (3)  🟡 中危 (5)  🟢 低危 (1)  📋 全部 (11)
```

点击某个标签 → 只展开对应严重度的 Collapse，隐藏其余；点击"全部"恢复。

实现方式：`useState` 维护 `filterSeverity: string | null`，渲染时过滤 `findingsBySeverity` 的 entries。

#### 2.3.2 Finding 卡片改进

每个 finding 卡片右上角增加复制按钮（`CopyOutlined`），点击后将该 finding 格式化为：

```
[${severity}] ${file}:${line} — ${title}
原因：${reason}
建议：${suggestion}
```

写入剪贴板。

#### 2.3.3 统计描述改为两行

将单行 `Descriptions` 拆成两行：第一行是风险等级 + 总结；第二行是发现问题数 + 涉及文件数 + 各严重度分布。

---
## 3. 范围边界

### 包含
- 仪表盘热力图、表格列修正
- 发起审查 Modal + 后端 PR/commit 列表 API
- 审查报告页过滤条 + 复制按钮

### 不包含
- 仓库详情页的列表选择改造（留待后续）
- GitHub OAuth 认证流程（假设 token 已配置在仓库/环境变量中）
- 实时通知/WebSocket 推送
- 移动端适配

---

## 4. 后端改动汇总

| # | 接口 | 类型 | 说明 |
|---|------|------|------|
| 1 | `GET /api/stats/overview` | 修改 | `recent_reviews` 中每条附带 `risk_level`（JOIN review_reports）；删除 `avg_risk_level` 字段 |
| 2 | `GET /api/stats/heatmap` | 新增 | 按仓库×月份聚合的风险热力图数据 |
| 3 | `GET /api/repos/{id}/prs` | 新增 | GitHub PR 列表（需 token） |
| 4 | `GET /api/repos/{id}/commits?limit=20` | 新增 | 本地 git log 最近 commits |

## 5. 前端改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `Dashboard.tsx` | 删平均风险卡片；热力图组件；修正表格列 |
| 2 | `ReviewDetail.tsx` | 严重度过滤条；Finding 复制按钮；统计重构 |
| 3 | `components/SubmitReviewModal.tsx` | 新增：发起审查弹窗 |
| 4 | `components/ReviewHeatmap.tsx` | 新增：热力图组件 |
| 5 | `RepoDetail.tsx` | 添加"发起审查"按钮（打开 Modal） |
| 6 | `RepoList.tsx` | 添加"发起审查"按钮（打开 Modal） |
| 7 | `Dashboard.tsx` | 添加"发起审查"按钮 |
| 8 | `types/index.ts` | 新增 HeatmapData、PRItem、CommitItem 类型；ReviewTask 扩展 risk_level |
| 9 | `api/reviews.ts` | 新增 `listPRs`、`listCommits` |
| 10 | `api/stats.ts` | 新增 `heatmap()` |

---

## 6. 热力图组件规格

### 数据加载

Dashboard mount 时调用 `statsApi.heatmap()`，获取热力图数据。

### 渲染逻辑

```tsx
<Table
  dataSource={heatmapData.repos}
  columns={[
    { title: "仓库", dataIndex: "repo_name", fixed: "left" },
    ...heatmapData.months.map(month => ({
      title: month,  // 显示为 "1月"、"2月" 等
      render: (_, repo) => {
        const cell = repo.cells.find(c => c.month === month);
        return <HeatmapCell cell={cell} onClick={...} />;
      }
    }))
  ]}
/>
```

`HeatmapCell` 是一个带背景色和 tooltip 的 div：
- 无数据：灰色 `#f0f0f0`
- 有数据：对应风险颜色，hover 显示 tooltip（审查次数 + 最高等级）
- 尺寸约 40×40px 的方块

### 边界情况
- 无仓库：显示 Empty 占位
- 无已完成审查：所有格子灰色
- 仓库数量超过单屏：表格可横向滚动（月份固定） + 纵向滚动

---

## 7. 发起审查 Modal 组件规格

### Props

```ts
interface SubmitReviewModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (reviewId: string) => void;  // 提交成功后回调
  preSelectedRepoId?: string;              // 可选：预设仓库（从仓库列表页打开时）
}
```

### 状态管理

```
repoId: string | null        — 选中的仓库
reviewType: 'pr' | 'local'   — 审查类型
selectedPR: number | null     — 选中的 PR 编号
selectedCommit: string | null — 选中的 commit hash
prs: PRItem[]                 — PR 列表
commits: CommitItem[]         — Commit 列表
loadingList: boolean          — 列表加载中
submitting: boolean           — 提交中
```

### 仓库下拉

使用 Ant Design `Select` 组件，`showSearch` + `filterOption` 支持搜索。数据来源：`GET /api/repos`。

### PR/Commit 列表

使用 Ant Design `List` 或小型 `Table`（单选），每行可点击选中，选中行高亮。

PR 列表显示：`#编号 — 标题 — 作者 — 创建时间`
Commit 列表显示：`短 hash — message — 作者 — 日期`

### 提交

调用 `reviewApi.submit(repoId, { review_type, pr_number, commit_hash })`。
成功 → `message.success("审查已提交")` → `onSuccess(task.id)` → 跳转 `/reviews/{task.id}`。

### 边界情况
- 未选仓库：禁止提交，仓库选择框标红提示
- PR 列表为空：显示"该仓库暂无 Open PR"
- 加载 PR 列表失败（无 token 或网络错误）：显示错误提示，降级到手输模式（保留现有 InputNumber）
- GitHub API 限流：返回 403 时提示"GitHub API 限流，请稍后重试或手动输入"

---

## 8. 风险与注意事项

1. **GitHub Token** — 调用 PR API 需要 token。当前系统在 `config.py` 中已有 `github_token` 字段，但需要确认仓库模型/配置中是否关联了 token。如果没有，`GET /api/repos/{id}/prs` 会在无 token 时返回 400 + 说明。

2. **热力图性能** — SQLite + `GROUP BY repo_id, month`，小规模（几十个仓库、几百条记录）无性能问题。

3. **向后兼容** — `OverviewStats.avg_risk_level` 删除后前端同步删字段，不会 broken（后端不再返回该字段，前端不再读取）。前后端同时部署即可。
