# 审查实时日志 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 审查进行中实时展示 workflow 节点进度和 LLM 工具调用日志，前端轮询渲染时间线。

**Architecture:** 后端在 workflow 节点和 `chat_with_tools` 中插桩写入 `review_logs` 表，通过模块级回调 `set_log_hook` 解耦 LLM 层与数据库层。前端轮询 `GET /api/reviews/{id}/logs`，与现有报告轮询合并为单个 `setInterval`。

**Tech Stack:** Python FastAPI + SQLAlchemy + SQLite / React 19 + TypeScript + Ant Design 6

## Global Constraints

- 不使用 emoji，纯文本标签
- `tool_args` 截断到 200 字符
- `chat_with_tools()` 每次工具调用写一条 log
- 日志轮询与报告轮询共用一个 `setInterval`
- 超过 50 条日志默认折叠，可展开
- 新日志从底部追加，容器最大高度 400px 超出滚动
- `tool_call` 步骤缩进显示

---

### Task 1: 后端 — ORM 模型 + Pydantic Schema

**Files:**
- Modify: `backend/app/models/repo.py`（追加 ReviewLog ORM 类）
- Modify: `backend/app/models/schemas.py`（追加 ReviewLogResponse）

**Interfaces:**
- Produces: `ReviewLog` ORM 类、`ReviewLogResponse` Pydantic schema

- [ ] **Step 1: 在 repo.py 末尾追加 ReviewLog ORM 模型**

```python
class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("review_tasks.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tool_args: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
```

- [ ] **Step 2: 在 schemas.py 末尾追加 ReviewLogResponse**

```python
class ReviewLogResponse(BaseModel):
    id: str
    task_id: str
    step: str
    level: str
    message: str
    tool_name: str | None = None
    tool_args: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: 验证后端启动**

```powershell
Set-Location E:\code-reviewer\backend; .venv\Scripts\python -c "from app.models.repo import ReviewLog; from app.models.schemas import ReviewLogResponse; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/repo.py backend/app/models/schemas.py
git commit -m "feat: 新增 ReviewLog ORM 模型和 ReviewLogResponse schema"
```

---

### Task 2: 后端 — llm.py 添加 log_hook 机制

**Files:**
- Modify: `backend/app/engine/llm.py`

**Interfaces:**
- Produces: `set_log_hook(hook: Callable | None)` 函数、`_log_hook` 模块变量
- `chat_with_tools()` 每次工具调用时调用 hook

- [ ] **Step 1: 修改 llm.py**

在文件顶部（`from app.config import settings` 之后）添加：

```python
from typing import Callable

_log_hook: Callable | None = None


def set_log_hook(hook: Callable | None):
    global _log_hook
    _log_hook = hook
```

在 `chat_with_tools()` 的工具执行循环中，每次调用 handler 后追加 hook 调用。找到循环内执行工具的那段代码（约第 98-105 行），在 `tool_result` 之后添加：

```python
                for tc in result["tool_calls"]:
                    handler = tool_handlers.get(tc["name"])
                    tool_result = handler(**tc["arguments"]) if handler else json.dumps({"error": f"unknown tool: {tc['name']}"})

                    # 日志插桩
                    if _log_hook:
                        try:
                            args_str = json.dumps(tc["arguments"], ensure_ascii=False)
                            if len(args_str) > 200:
                                args_str = args_str[:197] + "..."
                        except Exception:
                            args_str = str(tc["arguments"])[:200]
                        _log_hook(
                            step="tool_call",
                            level="info",
                            message=f"{tc['name']}: {args_str[:80]}",
                            tool_name=tc["name"],
                            tool_args=args_str,
                        )

                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result if isinstance(tool_result, str) else json.dumps(tool_result, ensure_ascii=False),
                    })
```

- [ ] **Step 2: 验证后端启动**

```powershell
Set-Location E:\code-reviewer\backend; .venv\Scripts\python -c "from app.engine.llm import set_log_hook; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/engine/llm.py
git commit -m "feat: llm.py 添加 log_hook 机制 — chat_with_tools 工具调用日志插桩"
```

---

### Task 3: 后端 — workflow.py 节点插桩

**Files:**
- Modify: `backend/app/engine/workflow.py`

**Interfaces:**
- Consumes: `set_log_hook` from Task 2
- Produces: 每个 node 函数开头/结尾写入 step 日志
- 通过 `state` 传递 `_log` callback

- [ ] **Step 1: 在每个 node 函数中插入日志**

给每个 node 函数末尾写入 `state['_log_hook'](...)` 调用。需要在 `_run_review_workflow` 初始化 state 时注入 log hook。

修改 `run_workflow()` 函数签名和实现：

```python
def run_workflow(
    repo_path: str,
    git_url: str = "",
    review_type: str = "pr",
    pr_number: int | None = None,
    commit_hash: str | None = None,
    base_branch: str | None = None,
    log_hook: Callable | None = None,
) -> dict:
    """运行审查 Workflow，返回报告 dict。"""
    initial_state: ReviewState = {
        "repo_id": repo_path,
        "git_url": git_url,
        "review_type": review_type,
        "pr_number": pr_number,
        "commit_hash": commit_hash,
        "base_branch": base_branch,
        "raw_diff": "",
        "changed_files": [],
        "review_plan": [],
        "file_context_cache": {},
        "findings": [],
        "reflection_round": 0,
        "need_more_context": False,
        "summary": "",
        "risk_level": "low",
        "crg_enabled": True,
        "impact_radius": None,
        "_log_hook": log_hook,
    }

    final_state = _graph.invoke(initial_state)
    return final_state.get("report", {})
```

修改 `_load_pr_node` — 在函数开头写入：

```python
    if hook := state.get("_log_hook"):
        hook(step="load_pr", level="info",
             message=f"正在获取代码变更... (type={review_type})")
    # ... 原有逻辑 ...
    if hook := state.get("_log_hook"):
        hook(step="load_pr", level="info",
             message=f"获取到 {len(state['changed_files'])} 个变更文件")
```

修改 `_collect_context_node` — 开头和结尾：

```python
    if hook := state.get("_log_hook"):
        hook(step="collect_context", level="info",
             message=f"正在收集文件上下文 ({len(state.get('changed_files', []))} 个文件)...")
    # ... 原有逻辑 ...
    source = "CRG" if state.get("crg_enabled") else "Normal"
    if hook := state.get("_log_hook"):
        hook(step="collect_context", level="info",
             message=f"已收集 {len(cache)} 个文件 ({source})")
```

修改 `_planning_node` — 开头和结尾：

```python
    if hook := state.get("_log_hook"):
        hook(step="planning", level="info", message="正在规划审查策略...")
    # ... 原有逻辑 ...
    if hook := state.get("_log_hook"):
        plan_str = ", ".join(state["review_plan"]) if state["review_plan"] else "(default style)"
        hook(step="planning", level="info",
             message=f"审查策略: {plan_str}")
```

修改 `_run_reviews_node` — 每个 reviewer 前后：

```python
    for reviewer_name in state.get("review_plan", []):
        reviewer = REVIEWER_REGISTRY.get(reviewer_name)
        if reviewer:
            try:
                if hook := state.get("_log_hook"):
                    hook(step="run_reviews", level="info",
                         message=f"正在执行 {reviewer_name}...")
                findings = reviewer.review(context)
                all_findings.extend(findings)
            except Exception as e:
                # ... existing error handling ...
```

修改 `_reflection_node` — 开头：

```python
    if hook := state.get("_log_hook"):
        hook(step="reflection", level="info",
             message=f"反思中 (第 {state.get('reflection_round', 0) + 1}/{settings.max_reflection_rounds} 轮)...")
```

修改 `_generate_report_node` — 开头：

```python
    if hook := state.get("_log_hook"):
        hook(step="generate_report", level="info", message="正在生成审查报告...")
```

- [ ] **Step 2: 验证后端启动**

```powershell
Set-Location E:\code-reviewer\backend; .venv\Scripts\python -c "from app.engine.workflow import run_workflow; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/engine/workflow.py
git commit -m "feat: workflow.py 各节点日志插桩"
```

---

### Task 4: 后端 — reviews.py 注入 hook + GET /logs API

**Files:**
- Modify: `backend/app/api/reviews.py`

**Interfaces:**
- Consumes: `set_log_hook` from Task 2, `ReviewLog` ORM from Task 1, `ReviewLogResponse` from Task 1, `run_workflow(log_hook=...)` from Task 3
- Produces: `GET /api/reviews/{task_id}/logs`

- [ ] **Step 1: 修改 _run_review_workflow 函数**

在 `_run_review_workflow` 中注入 log hook。修改 imports 和函数体：

在文件顶部添加 import：
```python
from app.models.repo import Repo, ReviewTask, ReviewReport, ReviewLog
from app.models.schemas import (
    ReviewCreate,
    ReviewTaskResponse,
    ReviewReportResponse,
    ReportContent,
    ReviewLogResponse,
)
from app.engine.llm import set_log_hook
```

修改 `_run_review_workflow` 函数，在调用 `run_workflow` 之前设置 hook：

```python
def _run_review_workflow(task_id: str):
    """后台运行审查 Workflow。"""
    from app.models.base import SessionLocal
    from app.engine.workflow import run_workflow

    db = SessionLocal()
    try:
        task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
        if not task:
            return

        task.status = "running"
        db.commit()

        repo = db.query(Repo).filter(Repo.id == task.repo_id).first()
        if not repo:
            raise ValueError("仓库不存在")

        # 注入日志 hook
        def log_hook(step: str, level: str, message: str,
                     tool_name: str | None = None, tool_args: str | None = None):
            try:
                log_entry = ReviewLog(
                    task_id=task_id,
                    step=step,
                    level=level,
                    message=message,
                    tool_name=tool_name,
                    tool_args=tool_args,
                )
                db.add(log_entry)
                db.commit()
            except Exception:
                pass  # 日志写入失败不影响审查流程

        set_log_hook(log_hook)

        # 写入开始日志
        log_hook(step="load_pr", level="info",
                 message=f"开始审查 (type={task.review_type})")

        # 运行审查引擎
        result = run_workflow(
            repo_path=repo.local_path,
            git_url=repo.git_url,
            review_type=task.review_type,
            pr_number=task.pr_number,
            commit_hash=task.commit_hash,
            base_branch=task.base_branch,
            log_hook=log_hook,
        )

        # 完成日志
        log_hook(step="generate_report", level="info", message="审查完成")

        report = ReviewReport(
            task_id=task.id,
            summary=result["summary"],
            risk_level=result["risk_level"],
            findings_json=json.dumps(result["findings"], ensure_ascii=False),
            stats_json=json.dumps(result["stats"], ensure_ascii=False),
        )
        db.add(report)
        task.status = "done"
        task.completed_at = datetime.now(UTC)
        db.commit()

    except Exception as e:
        db.rollback()
        task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
        if task:
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        set_log_hook(None)
        db.close()
```

- [ ] **Step 2: 追加 GET /logs 路由**

在 `reviews.py` 文件末尾追加：

```python
@router.get("/reviews/{task_id}/logs", response_model=list[ReviewLogResponse])
def get_review_logs(task_id: str, db: Session = Depends(get_db)):
    """获取审查任务的实时日志。"""
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="审查任务不存在")

    return (
        db.query(ReviewLog)
        .filter(ReviewLog.task_id == task_id)
        .order_by(ReviewLog.created_at.asc())
        .all()
    )
```

- [ ] **Step 3: 验证后端启动 + 路由注册**

```powershell
Set-Location E:\code-reviewer\backend; .venv\Scripts\python -c "from app.main import app; routes = [r.path for r in app.routes]; print('/api/reviews/{task_id}/logs' in routes)"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/reviews.py
git commit -m "feat: _run_review_workflow 注入 log_hook + GET /reviews/{id}/logs API"
```

---

### Task 5: 前端 — 类型 + API 扩展

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/reviews.ts`

**Interfaces:**
- Produces: `ReviewLog` interface, `reviewApi.logs()` method

- [ ] **Step 1: 在 types/index.ts 末尾追加 ReviewLog**

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

- [ ] **Step 2: 在 api/reviews.ts 添加 logs 方法**

```typescript
import type { ReviewTask, ReviewReportResponse, PRItem, CommitItem, ReviewLog } from "../types";

export const reviewApi = {
  // ... existing methods ...
  logs: (taskId: string) => api.get<ReviewLog[]>(`/reviews/${taskId}/logs`),
};
```

- [ ] **Step 3: 验证 TS 编译**

```powershell
Set-Location E:\code-reviewer\frontend; npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/reviews.ts
git commit -m "feat: 前端 ReviewLog 类型和 API 扩展"
```

---

### Task 6: 前端 — ReviewProgress 组件

**Files:**
- Create: `frontend/src/components/ReviewProgress.tsx`

**Interfaces:**
- Consumes: `ReviewLog` from Task 5
- Produces: `<ReviewProgress logs logPolling />`

- [ ] **Step 1: 创建 ReviewProgress.tsx**

```tsx
import { useEffect, useRef, useState } from "react";
import { Card, Button, Typography } from "antd";
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

interface Props {
  logs: ReviewLog[];
  logPolling: boolean;
}

export default function ReviewProgress({ logs, logPolling }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  const displayLogs = expanded ? logs : logs.slice(-MAX_VISIBLE);
  const hiddenCount = logs.length - MAX_VISIBLE;

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleTimeString("zh-CN", { hour12: false });
  };

  const isComplete = logs.length > 0 && logs[logs.length - 1].message === "审查完成";
  const isFailed = !logPolling && !isComplete && logs.length > 0;

  return (
    <Card
      title="审查进行中"
      style={{ marginBottom: 24 }}
      headStyle={
        isComplete
          ? { color: "#52c41a" }
          : isFailed
          ? { color: "#ff4d4f" }
          : undefined
      }
    >
      <div
        style={{
          maxHeight: 400,
          overflow: "auto",
          fontFamily: "monospace",
          fontSize: 13,
          lineHeight: 1.8,
        }}
      >
        {hiddenCount > 0 && !expanded && (
          <div style={{ marginBottom: 8 }}>
            <Button
              type="link"
              size="small"
              onClick={() => setExpanded(true)}
              style={{ padding: 0 }}
            >
              [展开全部 {logs.length} 条]
            </Button>
          </div>
        )}

        {displayLogs.map((log) => (
          <div
            key={log.id}
            style={{
              paddingLeft: log.step === "tool_call" ? 24 : 0,
              color: log.level === "error" ? "#ff4d4f" : "#333",
            }}
          >
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {formatTime(log.created_at)}
            </Typography.Text>{" "}
            {log.step !== "tool_call" && (
              <Typography.Text strong style={{ color: "#1677ff" }}>
                [{stepLabels[log.step] || log.step}]
              </Typography.Text>{" "}
            )}
            {log.message}
          </div>
        ))}

        {logPolling && !isComplete && (
          <div style={{ color: "#1677ff", marginTop: 4 }}>...</div>
        )}

        {isComplete && (
          <div style={{ color: "#52c41a", fontWeight: 600, marginTop: 4 }}>
            审查完成
          </div>
        )}

        {isFailed && (
          <div style={{ color: "#ff4d4f", fontWeight: 600, marginTop: 4 }}>
            审查失败
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: 验证 TS 编译**

```powershell
Set-Location E:\code-reviewer\frontend; npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ReviewProgress.tsx
git commit -m "feat: 新增 ReviewProgress 组件 — 审查实时日志时间线"
```

---

### Task 7: 前端 — ReviewDetail 集成 + 轮询合并

**Files:**
- Modify: `frontend/src/pages/ReviewDetail.tsx`

**Interfaces:**
- Consumes: `ReviewProgress` from Task 6, `reviewApi.logs()` from Task 5
- Produces: 合并后的 ReviewDetail 页面

- [ ] **Step 1: 修改 ReviewDetail.tsx**

在现有轮询逻辑中添加 logs 获取，将 `Card loading` 替换为 `ReviewProgress`。

改动点：

1. 添加 import：
```tsx
import ReviewProgress from "../components/ReviewProgress";
import type { ReviewLog } from "../types";
```

2. 添加 logs 状态：
```tsx
const [logs, setLogs] = useState<ReviewLog[]>([]);
const [logPolling, setLogPolling] = useState(true);
```

3. 修改 useEffect 轮询逻辑。当前有两个独立 then，改为合并：

```tsx
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
        // 如果已有最终日志且不再 loading，停止日志轮询
        const hasComplete = r.data.some(
          (l: ReviewLog) => l.message === "审查完成" || l.level === "error" && l.step === "generate_report"
        );
        if (hasComplete) {
          setLogPolling(false);
        }
      });
    };

    fetchAll();
    const interval = setInterval(fetchAll, 2000);

    return () => clearInterval(interval);
  }, [id]);
```

4. 将 loading 状态下的 `Card loading` 替换为：

```tsx
      {!report && polling && (
        <ReviewProgress logs={logs} logPolling={logPolling} />
      )}
```

原有的 failed 和 "未找到报告" 分支保持不变，放在 ReviewProgress 之后。

5. 在 report 展示区（findings 列表上方），审查完成后仍可显示已折叠的日志摘要。在 report 的 `<>` 开头加上已完成状态：

```tsx
      {report && logs.length > 0 && !polling && (
        <ReviewProgress logs={logs} logPolling={false} />
      )}
```

- [ ] **Step 2: 验证 TS 编译**

```powershell
Set-Location E:\code-reviewer\frontend; npx tsc --noEmit
```

- [ ] **Step 3: 手动验证**（需要后端运行）

启动后端，发起一次审查，观察前端 ReviewDetail 页面是否实时展示日志。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ReviewDetail.tsx
git commit -m "feat: ReviewDetail 集成 ReviewProgress + 轮询合并"
```

---

## Plan Self-Review

### Coverage Check
- [x] Spec 3.1: `review_logs` 表 → Task 1 (ORM)
- [x] Spec 3.2: `ReviewLogResponse` schema → Task 1
- [x] Spec 4.1: 插桩点表 → Task 3 (workflow.py) + Task 4 (reviews.py 开始/完成日志)
- [x] Spec 4.2: `set_log_hook` 机制 → Task 2 (llm.py)
- [x] Spec 5: `GET /api/reviews/{task_id}/logs` → Task 4
- [x] Spec 6.2: 渲染样式（缩进、滚动、颜色） → Task 6
- [x] Spec 6.3: 折叠逻辑 (>50 条) → Task 6
- [x] Spec 6.5: 轮询合并 → Task 7
- [x] Spec 7: 前端类型 + API → Task 5
- [x] Spec 9: 约束（无 emoji、截断、共用 setInterval） → 贯穿各 Task

### Placeholder Scan
- [x] 无 TBD/TODO
- [x] 所有代码块完整

### Type Consistency
- [x] `ReviewLog` ORM 字段 ↔ `ReviewLogResponse` schema 字段 ↔ 前端 `ReviewLog` interface 字段完全对齐
- [x] `_log_hook` 签名统一：`(step, level, message, tool_name?, tool_args?)`
- [x] `run_workflow(log_hook=...)` → state["_log_hook"] → node 函数内统一访问模式
