# Code Reviewer — 系统设计

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 | Dashboard SPA |
| 后端 API | Python 3.11+ FastAPI | REST API + 异步 Task 管理 |
| 审查引擎 | LangGraph + LangChain | Review Workflow 编排 |
| 代码图谱 | code-review-graph (pip 库) | 爆炸半径分析 |
| 数据库 | SQLite (开发) / PostgreSQL (生产) | Review Task + Report 持久化 |
| 异步队列 | asyncio + BackgroundTasks | FastAPI 内置异步 |

## 项目结构

```
E:\code-reviewer\
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置管理
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── repos.py         # 仓库管理 CRUD
│   │   │   ├── reviews.py       # 审查提交 + 结果查询
│   │   │   └── stats.py         # 统计面板 API
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── repo.py          # Repository ORM 模型
│   │   │   ├── review.py        # ReviewTask + ReviewReport ORM
│   │   │   └── schemas.py       # Pydantic 请求/响应 Schema
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── workflow.py      # LangGraph Workflow 定义
│   │   │   ├── state.py         # ReviewState
│   │   │   ├── nodes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── load_pr.py
│   │   │   │   ├── planning.py
│   │   │   │   ├── collect_context.py
│   │   │   │   ├── run_reviews.py
│   │   │   │   ├── reflection.py
│   │   │   │   └── generate_report.py
│   │   │   ├── reviewers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py      # Reviewer 基类
│   │   │   │   ├── security.py
│   │   │   │   ├── performance.py
│   │   │   │   └── style.py
│   │   │   └── tools/
│   │   │       ├── __init__.py
│   │   │       ├── registry.py  # @register_tool 装饰器
│   │   │       ├── get_diff.py
│   │   │       ├── read_file.py
│   │   │       ├── ruff.py
│   │   │       ├── git_blame.py
│   │   │       └── crg_tools.py # CRG 集成
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── review_service.py    # 审查任务调度
│   │       └── stats_service.py     # 统计计算
│   ├── prompts/                 # Jinja2 Prompt 模板
│   │   ├── security.j2
│   │   ├── performance.j2
│   │   └── style.j2
│   ├── tests/
│   ├── pyproject.toml
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api/
│   │   │   ├── client.ts         # axios 实例
│   │   │   ├── repos.ts          # 仓库 API
│   │   │   ├── reviews.ts        # 审查 API
│   │   │   └── stats.ts          # 统计 API
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx     # 统计首页
│   │   │   ├── RepoList.tsx      # 仓库列表
│   │   │   ├── RepoDetail.tsx    # 仓库详情 + 审查历史
│   │   │   ├── ReviewDetail.tsx  # 单次审查报告
│   │   │   └── NewReview.tsx     # 提交审查
│   │   ├── components/
│   │   │   ├── Layout.tsx        # 全局布局（侧边栏 + 顶栏）
│   │   │   ├── SeverityTag.tsx   # 严重级别标签
│   │   │   ├── FindingCard.tsx   # 审查发现卡片
│   │   │   ├── RiskBadge.tsx     # 风险等级徽章
│   │   │   ├── StatsChart.tsx    # 统计图表
│   │   │   └── FileTree.tsx      # 文件变更树
│   │   ├── hooks/
│   │   │   ├── usePolling.ts     # 轮询 hook（审查结果）
│   │   │   └── useStats.ts       # 统计数据 hook
│   │   └── types/
│   │       └── index.ts          # TypeScript 类型定义
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── docs/
│   ├── CONTEXT.md
│   ├── adr/
│   │   ├── 0001-reflection-loop-termination.md
│   │   └── 0002-planning-trigger-dual-strategy.md
│   ├── crg-integration-plan.md
│   └── system-design.md          # ← 本文件
│
└── .gitignore
```

## 数据库设计

### repositories 表

| 列 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| name | VARCHAR(255) | 仓库名 |
| git_url | VARCHAR(500) | 远程地址 |
| local_path | VARCHAR(500) | 本地路径 |
| default_branch | VARCHAR(100) | 默认 "main" |
| created_at | DATETIME | |

### review_tasks 表

| 列 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| repo_id | FK → repositories.id | |
| review_type | VARCHAR(20) | "pr" / "local" |
| pr_number | INT NULL | GitHub PR 场景 |
| commit_hash | VARCHAR(40) NULL | local 场景 |
| base_branch | VARCHAR(100) NULL | PR 场景 |
| status | VARCHAR(20) | pending / running / done / failed |
| reflection_rounds | INT DEFAULT 0 | Reflection 循环次数 |
| created_at | DATETIME | |
| completed_at | DATETIME NULL | |

### review_reports 表

| 列 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| task_id | FK → review_tasks.id | |
| summary | TEXT | 审查摘要 |
| risk_level | VARCHAR(10) | low / medium / high / critical |
| findings_json | TEXT | Finding[] JSON |
| stats_json | TEXT | 统计快照 |
| created_at | DATETIME | |

## API 设计

### 仓库管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/repos` | 仓库列表 |
| POST | `/api/repos` | 添加仓库 |
| GET | `/api/repos/{id}` | 仓库详情 |
| DELETE | `/api/repos/{id}` | 删除仓库 |
| POST | `/api/repos/{id}/sync` | 同步（git pull） |

### 审查任务

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/repos/{id}/reviews` | 提交审查（PR 或 local commit） |
| GET | `/api/repos/{id}/reviews` | 审查历史列表 |
| GET | `/api/reviews/{id}` | 审查详情（轮询用） |
| GET | `/api/reviews/{id}/report` | 审查报告 |

### 统计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/stats/overview` | 总览（总次数/风险分布/趋势） |
| GET | `/api/stats/repos/{id}` | 单仓库统计 |
| GET | `/api/stats/hotspots` | 热点文件排名 |

### 请求/响应示例

```json
// POST /api/repos/{id}/reviews  (PR 模式)
{
  "review_type": "pr",
  "pr_number": 42
}

// POST /api/repos/{id}/reviews  (local 模式)
{
  "review_type": "local",
  "commit_hash": "a1b2c3d"
}

// Response (201)
{
  "review_id": "uuid",
  "status": "pending"
}

// GET /api/reviews/{id}/report (审查完成后)
{
  "review_id": "uuid",
  "status": "done",
  "report": {
    "summary": "...",
    "risk_level": "medium",
    "findings": [
      {
        "severity": "high",
        "file": "src/auth.py",
        "line": 42,
        "title": "SQL 注入风险",
        "reason": "直接拼接用户输入到 SQL 查询",
        "suggestion": "使用参数化查询"
      }
    ],
    "stats": {
      "total_findings": 5,
      "by_severity": {"critical": 0, "high": 2, "medium": 2, "low": 1},
      "impacted_files": 12,
      "test_gaps": 3
    }
  }
}
```

## 前端页面设计

### 路由

| 路径 | 页面 | 说明 |
|---|---|---|
| `/` | Dashboard | 统计首页 |
| `/repos` | RepoList | 仓库管理 |
| `/repos/:id` | RepoDetail | 仓库详情 + 审查提交 |
| `/reviews/:id` | ReviewDetail | 审查报告 |

### Dashboard（首页）

```
┌─────────────────────────────────────────────────┐
│  Code Reviewer                        [+新审查]  │
├──────────┬──────────┬──────────┬────────────────┤
│ 总审查次数 │ 本月审查  │ 平均风险  │ 活跃仓库数      │
│   127    │   23     │  MEDIUM  │     5         │
├──────────┴──────────┴──────────┴────────────────┤
│  风险分布 (饼图)         热点文件 Top 10 (柱状图)   │
│  ┌──────────────┐      ┌──────────────────────┐ │
│  │ critical  3% │      │ src/auth.py      12  │ │
│  │ high     15% │      │ src/api/main.py   8  │ │
│  │ medium   42% │      │ ...                  │ │
│  │ low      40% │      │                      │ │
│  └──────────────┘      └──────────────────────┘ │
├─────────────────────────────────────────────────┤
│  最近审查                                       │
│  ┌─────────────────────────────────────────────┐│
│  │ #42 · my-repo · PR #128 · HIGH · 2分钟前    ││
│  │ #41 · backend · local · MEDIUM · 1小时前    ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

### RepoDetail（仓库详情）

```
┌─────────────────────────────────────────────────┐
│  ← 返回    my-repo                    [提交审查]  │
│  https://github.com/xxx/my-repo                 │
├─────────────────────────────────────────────────┤
│  [审查历史]                                      │
│  ┌──────┬────────┬────────┬──────┬─────────────┐│
│  │ 类型  │ 标识    │ 风险    │ 时间  │ 操作         ││
│  ├──────┼────────┼────────┼──────┼─────────────┤│
│  │ PR   │ #42    │ HIGH   │ 2分钟 │ 查看报告      ││
│  │ Local│ abc123 │ MEDIUM │ 1小时 │ 查看报告      ││
│  └──────┴────────┴────────┴──────┴─────────────┘│
└─────────────────────────────────────────────────┘
```

### ReviewDetail（审查报告）

```
┌─────────────────────────────────────────────────┐
│  ← 返回    审查报告 #42                           │
│  仓库: my-repo · PR #128 · 风险: HIGH            │
├─────────────────────────────────────────────────┤
│  📊 摘要                                         │
│  本次审查发现 5 个问题（2 高危, 2 中危, 1 低危）      │
│  涉及 12 个文件，其中 3 个函数缺少测试覆盖            │
├─────────────────────────────────────────────────┤
│  🔴 高危                                         │
│  ┌─────────────────────────────────────────────┐│
│  │ src/auth.py:42  SQL 注入风险                 ││
│  │ 直接拼接用户输入到 SQL 查询                     ││
│  │ 💡 使用参数化查询替代字符串拼接                  ││
│  └─────────────────────────────────────────────┘│
│  🟡 中危                                         │
│  ┌─────────────────────────────────────────────┐│
│  │ src/api/handler.py:128  异常未处理             ││
│  │ ...                                          ││
│  └─────────────────────────────────────────────┘│
│  🟢 低危                                         │
│  ┌─────────────────────────────────────────────┐│
│  │ ...                                          ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

## 数据流

```
用户提交审查
    │
    ▼
Frontend: POST /api/repos/{id}/reviews
    │
    ▼
Backend: 创建 ReviewTask (status=pending)
    │  返回 review_id → Frontend 开始轮询 GET /api/reviews/{id}
    │
    ▼
Backend: BackgroundTasks 启动 LangGraph Workflow
    │
    ├─ Load PR:   GetDiff (GitHub API or local git)
    ├─ Planning:  LLM + CRG HubNodes → Review Plan
    ├─ Collect:   CRG.get_review_context → 爆炸半径 → ReadFile(精准15个文件)
    ├─ Run:       Reviewer 并行执行 → Findings
    ├─ Reflect:   检查 Findings 完整性 → 回退或继续
    └─ Generate:  聚合 Findings → Report
    │
    ▼
Backend: 存入 review_reports 表，更新 task status=done
    │
    ▼
Frontend: 轮询到 status=done → GET /api/reviews/{id}/report → 渲染报告
```

## 下一步实施顺序

| 阶段 | 内容 |
|---|---|
| 1 | 后端骨架：FastAPI 入口 + 数据库模型 + 仓库 CRUD API |
| 2 | 审查引擎：LangGraph Workflow + Tool Registry + 基础 Reviewer |
| 3 | CRG 集成：按 crg-integration-plan.md 实施 |
| 4 | 前端骨架：React + Vite + Ant Design + 路由 |
| 5 | 前端页面：Dashboard + RepoList + NewReview + ReviewDetail |
| 6 | 联调 + 统计面板 |
