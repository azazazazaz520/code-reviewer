# 审查实时日志 — 设计规格

日期：2026-07-20
状态：已确认

---

## 1. 背景

当前审查流程在后台线程跑 LangGraph workflow，前端只能轮询 `/report` 看最终结果。审查进行中时用户看到的是一个 loading spinner，完全不知道里面在做什么、进展到哪一步、有没有卡住。

需要在审查进行中实时展示：当前执行到哪个步骤、调用了哪些工具。

## 2. 方案

事件日志表 + 轮询。

- 后端在 workflow 节点和 LLM 工具调用处插桩写入 `review_logs` 表
- 前端轮询 `GET /api/reviews/{id}/logs`（2 秒间隔，与 `/report` 共用同一轮询）
- 审查结束后日志保留，方便事后回溯

## 3. 数据模型

### 3.1 新表 `review_logs`

```sql
CREATE TABLE review_logs (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES review_tasks(id) ON DELETE CASCADE,
    step        TEXT NOT NULL,
    level       TEXT DEFAULT 'info',
    message     TEXT NOT NULL,
    tool_name   TEXT,
    tool_args   TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

字段说明：

| 字段 | 说明 |
|------|------|
| `step` | 节点名: `load_pr`, `collect_context`, `planning`, `run_reviews`, `reflection`, `generate_report`, `tool_call` |
| `level` | `info` 或 `error` |
| `message` | 用户可读描述 |
| `tool_name` | 仅 `tool_call` 步骤有值，如 `ReadFile` |
| `tool_args` | 仅 `tool_call` 步骤有值，JSON 字符串，大参数截断到 200 字符 |

### 3.2 Pydantic Schema

```python
class ReviewLogResponse(BaseModel):
    id: str
    task_id: str
    step: str
    level: str
    message: str
    tool_name: str | None = None
    tool_args: str | None = None
    created_at: str

    model_config = {"from_attributes": True}
```

## 4. 日志插桩

### 4.1 插桩点

| 位置 | step | message 示例 |
|------|------|-------------|
| `_load_pr_node` 开始 | `load_pr` | "正在获取代码变更..." |
| `_load_pr_node` 结束 | `load_pr` | "获取到 N 个变更文件" |
| `_collect_context_node` 开始 | `collect_context` | "正在收集文件上下文..." |
| `_collect_context_node` 结束 | `collect_context` | "已收集 N 个文件 (CRG/Normal)" |
| `_planning_node` 开始 | `planning` | "正在规划审查策略..." |
| `_planning_node` 结束 | `planning` | "审查策略: style_reviewer, security_reviewer" |
| `_run_reviews_node` 每个 reviewer | `run_reviews` | "正在执行 style_reviewer..." |
| `_reflection_node` 开始 | `reflection` | "反思中 (第 N/M 轮)..." |
| `_generate_report_node` | `generate_report` | "正在生成审查报告..." |
| 审查完成 | — | "审查完成" |
| `chat_with_tools` 工具调用 | `tool_call` | "ReadFile: src/app.py" |

### 4.2 日志写入机制

`llm.py` 不直接依赖数据库层。通过模块级全局回调注入：

```python
# llm.py
_log_hook: Callable | None = None

def set_log_hook(hook: Callable | None):
    global _log_hook
    _log_hook = hook
```

`chat_with_tools()` 中每次 exec tool 时调用 `_log_hook(...)`。

`workflow.py` 的 `_run_review_workflow()` 在运行前注入 hook，运行后清除。

## 5. API

**`GET /api/reviews/{task_id}/logs`**

返回日志列表，按 `created_at` 升序：

```json
[
  {
    "id": "uuid",
    "task_id": "uuid",
    "step": "load_pr",
    "level": "info",
    "message": "正在获取代码变更...",
    "tool_name": null,
    "tool_args": null,
    "created_at": "2026-07-20T12:30:01"
  }
]
```

响应类型：`list[ReviewLogResponse]`

## 6. 前端组件 `ReviewProgress`

### 6.1 位置

ReviewDetail 页面 `!report && polling` 状态下展示，替换当前的单行 `Card loading`。

### 6.2 渲染

```
[审查进行中]

  12:30:01  正在获取代码变更...
  12:30:03  正在收集文件上下文 (15 个文件)
  12:30:05  规划审查策略: style_reviewer, security_reviewer
  12:30:06  正在执行 style_reviewer
  12:30:07    ReadFile: src/app.py
  12:30:08    ReadFile: src/utils.py
  12:30:09    GetHubNodes
  12:30:15  正在执行 security_reviewer
  12:30:16    ReadFile: src/auth.py
  12:30:20  反思中 (第 1/3 轮)
  12:30:22  正在生成审查报告
  12:30:23  审查完成
```

- 新日志从底部追加
- 容器最大高度 400px，超出滚动
- `tool_call` 步骤缩进显示
- 审查完成时最后一条变绿色
- 不使用 emoji

### 6.3 折叠逻辑

超过 50 条日志时，默认显示最近 50 条 + 底部 "[展开全部 N 条]" 按钮。点击后展开所有。

### 6.4 Props

```ts
interface ReviewProgressProps {
  logs: ReviewLog[];
  loading: boolean;
}
```

### 6.5 轮询合并

当前 ReviewDetail 已有两个间隔轮询：`/reviews/{id}` (status) 和 `/reviews/{id}/report` (报告)。日志轮询合并到同一个 `setInterval` 中，一次发三个请求，避免多个 timer。

## 7. 类型定义

### 前端 `ReviewLog`

```typescript
export interface ReviewLog {
  id: string;
  task_id: string;
  step: string;
  level: string;
  message: string;
  tool_name?: string | null;
  tool_args?: string | null;
  created_at: string;
}
```

### 前端 API

```typescript
logs: (taskId: string) => api.get<ReviewLog[]>(`/reviews/${taskId}/logs`)
```

## 8. 范围边界

### 包含
- `review_logs` 表 + ORM 模型
- 8 个 workflow 节点的开始/结束日志
- `chat_with_tools()` 工具调用日志
- `GET /api/reviews/{id}/logs` API
- `ReviewProgress` 组件
- ReviewDetail 集成 + 轮询合并

### 不包含
- 日志持久化清理策略（日志随 task 级联删除，无需额外清理）
- WebSocket/SSE 实时推送
- 日志搜索/过滤
- 日志导出

## 9. 约束

- 不使用 emoji，纯文本标签
- `tool_args` 截断到 200 字符，避免存超大 JSON
- `chat_with_tools()` 每次工具调用写一条 log，不区分 round
- 日志轮询与报告轮询共用一个 `setInterval`
