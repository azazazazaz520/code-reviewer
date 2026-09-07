# Workflow 模块化实施方案

> 本文记录的旧模块化方案已由 2026-09-07 的精简流程取代。当前实现以
> `prepare_review.py` 合并规划、确定性校验和上下文准备，以 `run_reviews.py`
> 执行 Reviewer 批次；`collect_context.py` 与 `reflection.py` 已删除。以下内容仅保留
> 作为历史决策记录，新的修改应遵循 `docs/system-design.md` 和 ADR 0003。

## 1. 方案定位

本文档记录 `backend/app/engine/workflow.py` 的模块化拆分方案。目标是落实
`AGENTS.md` 的「后端 Workflow 只负责编排」原则与 `system-design.md` 中已规划的
`engine/nodes/` 目录结构，使各节点逻辑可以独立测试，避免审查流程逻辑继续堆积
在单个 Workflow 函数中。

## 2. 拆分前的问题

| 问题 | 位置 | 影响 |
| --- | --- | --- |
| 单文件 545 行，7 个节点全部内聚在 workflow.py | `workflow.py` | 变更评审流程需要阅读整个文件；无法对单个节点独立测试 |
| 报告聚合、质量指标计算等业务逻辑内联在节点中 | `_generate_report_node`、`_run_reviews_node` | 违反「Workflow 只负责编排」；测试只能通过整个图或复制 state 断言 |
| Node 编号注释混乱 | `validate_changes` / `collect_context` 均标注 "Node 3" | 误导阅读者 |
| `_try_crg_context` 的静默降级逻辑与图谱生命周期耦合在节点中 | `_collect_context_node` | CRG 策略无法独立验证 |

## 3. 目标结构

```
backend/app/engine/
├── workflow.py              # 只保留 _build_graph + run_workflow + 初始 state（约 135 行）
├── crg.py                   # try_crg_context()：CRG 图谱构建与影响半径分析
├── quality.py               # compute_quality_metrics() / build_quality_checks() 纯函数
├── reporting.py             # build_report() 及 severity/risk/status 推导纯函数
└── nodes/
    ├── __init__.py          # 节点统一导出（workflow.py 只从这里导入）
    ├── load_pr.py           # load_pr_node：加载 diff 与变更文件（快照优先）
    ├── planning.py          # planning_node：生成 review_plan 与 change_scopes
    ├── validate_changes.py  # validate_changes_node：确定性校验器执行
    ├── collect_context.py   # collect_context_node：分批读取文件上下文 + CRG 硬触发
    ├── run_reviews.py       # run_reviews_node：串行执行 Reviewer + FindingGate
    ├── reflection.py        # reflection_node + should_retry（ADR 0001 终止条件）
    └── generate_report.py   # generate_report_node：调用 reporting 并写回 state
```

## 4. 拆分的约束

- 节点函数签名统一为 `(state: ReviewState) -> ReviewState`，与 LangGraph 兼容。
- 节点只读写 `ReviewState` 中职责范围内的字段（字段归属见 `app/engine/state.py`）。
- 节点之间互不导入，`workflow.py` 是唯一导入全部节点的模块，避免循环依赖。
- `reviewers/__init__.py` 的 `REVIEWER_REGISTRY` 是共享 dict，测试通过原地
  `clear() + update()` 替换，避免 `from ... import` 绑定旧对象导致 mock 失效。
- `build_report` 保持与前端 `ReviewReportResponse` / `ReviewChanges`（
  `backend/app/models/schemas.py`）一致的契约字段；修改字段必须同步检查前端类型。

## 5. 行为一致性

- 拆分不改变 LangGraph 拓扑与运行入口：`run_workflow()` 的签名、初始 state、
  snapshot 生命周期（创建与 finally cleanup）原样保留。
- `quality_metrics` 与 `checks` 的生成顺序、内容与拆分前一致：
  workflow_errors 派生 check 先于 finding_gate / finding_context check。
- CRG 任何失败仍静默降级（返回 False），由 `collect_context_node` 回退为普通
  候选集合。

## 6. 测试策略

| 测试文件 | 覆盖 |
| --- | --- |
| `backend/tests/test_nodes.py` | 7 个节点的最小 state 输入输出契约；CRG 高/低影响分支；Reviewer 成功/失败分支；reflection 四分支 |
| `backend/tests/test_quality.py` | 质量指标计数、截断统计、门槛检查派生 |
| `backend/tests/test_reporting.py` | severity 聚合、risk/status/summary 推导、report/changes/stats 契约字段 |
| `backend/tests/test_review_quality.py` | 原有全链路测试改为从 `app.engine.nodes` 导入节点，注册表替换方式同步更新 |

运行命令（仓库根目录）：

```
$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -q
```

## 7. 后续可选演进

- Reviewer 并行执行：`run_reviews_node` 当前为串行；并行化需以线程池执行
  `reviewer.review()`，并确认 `ReviewLogBuffer` 在跨线程 flush 下日志不丢失。
- 节点级超时与重试策略可集中在 `run_reviews` 内部，不扩散到其他节点。
