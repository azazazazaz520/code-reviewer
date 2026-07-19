# CRG 集成实施计划

## 概述

将 [code-review-graph](https://github.com/tirth8205/code-review-graph) 作为 Python 库引入，用于精准上下文获取和代码图谱分析。核心价值：替换 Collect Context 阶段的"LLM 猜文件 → 批量读取"流程，改为"爆炸半径分析 → 精准读取 15 个文件"。

## 依赖

```toml
# pyproject.toml
[project]
dependencies = [
    "langgraph",
    "langchain",
    "pydantic",
    "jinja2",
    "code-review-graph>=2.3",  # ← 新增
]
```

## 架构改动点

### 1. ReviewState 扩展

新增字段：

```python
class ReviewState(TypedDict):
    # ... 原有字段 ...
    # 新增
    crg_enabled: bool              # CRG 图是否已构建
    crg_store_path: str | None     # CRG SQLite 数据库路径
    impact_radius: dict | None     # get_impact_radius 的缓存结果
    hub_nodes: list[dict] | None   # 热点节点缓存
```

### 2. 新增 Tool：CRGTools (4 个)

文件：`src/tools/crg_tools.py`

```python
from tools.registry import registry
from code_review_graph.tools.review import get_review_context
from code_review_graph.tools.analysis_tools import (
    get_hub_nodes_func,
    get_bridge_nodes_func,
    get_suggested_questions_func,
)

@registry.register(name="GetReviewContext", toolset="file")
def get_review_context_tool(changed_files, max_depth=2, ...):
    """获取变更文件的爆炸半径 + 源码片段。替代 Collect Context 的批量文件读取。"""
    return get_review_context(changed_files=changed_files, max_depth=max_depth, ...)

@registry.register(name="GetHubNodes", toolset="file")
def get_hub_nodes_tool(repo_root=None, top_n=10):
    """获取代码库中连接度最高的节点（架构热点）。Planning 阶段用于判断风险等级。"""
    return get_hub_nodes_func(repo_root=repo_root, top_n=top_n)

@registry.register(name="GetBridgeNodes", toolset="file")
def get_bridge_nodes_tool(repo_root=None, top_n=10):
    """获取架构咽喉节点。改动这些节点的爆炸半径最大。"""
    return get_bridge_nodes_func(repo_root=repo_root, top_n=top_n)

@registry.register(name="GetSuggestedQuestions", toolset="file")
def get_suggested_questions_tool(repo_root=None):
    """基于图谱分析自动生成审查问题。Reflection 阶段用于检查遗漏。"""
    return get_suggested_questions_func(repo_root=repo_root)
```

### 3. Collect Context Node 改造（核心改动）

**现状（设计）**:
```
LLM(prompt="分析这个 diff，列出需要读取的文件")
→ [file_a.py, file_b.py, file_c.py, ...]
→ 并行 ReadFile(file_a), ReadFile(file_b), ...
→ 写入 file_context_cache
```

**改造后**:
```python
def collect_context_node(state: ReviewState) -> ReviewState:
    changed_files = state["changed_files"]

    # Step 1: 用 CRG 获取爆炸半径（确定性计算，不用 LLM）
    if state["crg_enabled"]:
        context = get_review_context(
            changed_files=changed_files,
            max_depth=2,
            include_source=True,
            detail_level="standard",
        )
        # context 已包含:
        #   - impacted_files: 受影响的文件列表（精准，~15 个）
        #   - source_snippets: 变更函数的源码片段
        #   - changed_nodes / impacted_nodes: 变更和受影响的 AST 节点
        #   - edges: 调用/继承/依赖边
        state["impact_radius"] = context
        files_to_read = context["context"]["impacted_files"]
    else:
        # 降级：原有 LLM 猜文件流程
        files_to_read = _llm_guess_files(state["diff"])

    # Step 2: 补充读取 CRG 没覆盖的文件（如配置文件、README）
    #          LLM 仍然可以追加需要读取的文件
    extra_files = _llm_suggest_extra_files(state["diff"], files_to_read)
    all_files = list(set(files_to_read + extra_files))

    # Step 3: 并行读取所有文件
    state["file_context_cache"] = _parallel_read_files(all_files)

    return state
```

### 4. Planning Node 增强

在原有双层策略基础上，增加 CRG-based 硬触发器：

```python
def planning_node(state: ReviewState) -> ReviewState:
    plan = LLM_analyze_diff(state["diff"])  # 软策略（不变）

    # 正则硬触发器（原有，不变）
    plan = _apply_regex_triggers(plan, state["diff"])

    # 新增：CRG 热点触发器
    if state["crg_enabled"] and state.get("hub_nodes"):
        changed_funcs = _extract_changed_functions(state["diff"])
        hub_names = {h["qualified_name"] for h in state["hub_nodes"][:5]}
        if changed_funcs & hub_names:
            plan.append("security_reviewer")   # 热点变更 → 强制安全审查
            plan.append("performance_reviewer") # 热点变更 → 强制性能审查

    state["review_plan"] = deduplicate(plan)
    return state
```

### 5. 图谱生命周期

```
Workflow 启动
    │
    ├─ 检查 .code-review-graph/ 目录是否存在
    │   ├─ 不存在 → code-review-graph build（首次构建，~10s for 500 files）
    │   └─ 存在   → 增量更新（< 2s for 2900 files）
    │
    ├─ 设置 state["crg_enabled"] = True
    └─ 继续正常 Workflow
```

实现为 Workflow 的初始化步骤（在 Load PR 之后、Planning 之前）。

### 6. 错误处理（遵循 CONTEXT.md 的 WorkflowError 分类）

| 场景 | 分类 | 处理 |
|---|---|---|
| CRG 未安装 (ImportError) | 可恢复 | `crg_enabled=False`，降级到原 LLM 流程 |
| 图未构建 | 可恢复 | 自动触发 `code-review-graph build` |
| 图构建失败 | 可恢复 | `crg_enabled=False`，记录 warning |
| CRG 查询超时 | 部分失败 | 跳过该 Tool，Reviewer 无此 Tool 可调用 |
| CRG 返回空结果 | 可恢复 | 降级到原流程 |

### 7. Tool Data Source 适配

遵循 CONTEXT.md 的 Tool Data Source 设计：

```python
# CRG Tools 也区分 PR 和 Local 两种数据源：
# - PR 模式：图中文件路径为 repo 内相对路径，与 GitHub API 路径对齐
# - Local 模式：图中文件路径为绝对路径，与本地文件系统对齐
# 通过 repo_root 参数控制
```

## 实施顺序

| 步骤 | 内容 | 预估工作量 |
|---|---|---|
| 1 | 初始化项目骨架（pyproject.toml, src/, tests/） | 基础 |
| 2 | 实现 Tool Registry + 基础 Tools（ReadFile, GetDiff） | 基础 |
| 3 | **集成 CRG：创建 crg_tools.py（4 个 Tool）** | 小 |
| 4 | **改造 Collect Context Node（核心）** | 大 |
| 5 | 实现 Planning Node（含 CRG 热点触发器） | 中 |
| 6 | 实现 Reviewer 基类 + 示例 Reviewer | 中 |
| 7 | 实现 Run Reviews + Reflection + Generate Report | 中 |
| 8 | 图谱生命周期管理（build / 增量更新） | 小 |

## 不引入 CRG 的部分

以下保持原设计，不受 CRG 影响：

- **Finding / Review Report 格式** — CRG 不参与输出，只提供输入
- **Reflection Loop 终止策略** — ADR 0001 的硬限制+软判断不变
- **Planning Trigger 双层策略** — ADR 0002 的软策略+硬触发器不变，仅在硬触发器中增加一个规则引擎条件
- **LLM Provider 抽象层** — 完全独立
- **Review Task 异步模型** — 完全独立
- **Prompt Template 系统** — 完全独立
