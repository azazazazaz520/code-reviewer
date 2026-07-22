# Code Review Agent

基于 LangGraph 的自动化 GitHub Pull Request 审查 Agent 系统。通过自主规划、工具调用、上下文检索和循环反思，输出结构化 Review Report。

## Language

**Reviewer**:
一个 LLM 调用 + 一组关联 Tool 的绑定体。Reviewer 接收 Context，通过 LLM 驱动的主观判断分析代码，输出 Findings。它是分析决策层，不直接执行数据获取操作。通过 Pydantic BaseModel 定义契约，使用 `@register_reviewer` 装饰器注册到全局 Registry。
_例如_: Security Reviewer = Security Prompt + [ReadFile, SearchSymbol, Ruff, GitBlame]
_Avoid_: 审查器、检查器

**Tool**:
一个单一职责的客观数据获取或操作单元。Tool 不包含 LLM 逻辑，被 Reviewer 或 Workflow Node 调用以获取代码、运行分析、执行测试等。它是数据层。
_例如_: GetDiff, ReadFile, Ruff, RunTests, GitBlame
_Avoid_: 工具函数、辅助函数

**Finding**:
Reviewer 输出的单个审查发现，包含严重级别、文件、行号、标题、原因和建议。是所有 Reviewer 的统一输出格式。
_Avoid_: 问题、缺陷、issue

**Review Plan**:
Planning Node 根据 PR Diff 内容动态生成的审查策略，决定执行哪些 Reviewer。不同 PR 产生不同的 Plan。
_Avoid_: 审查策略、检查清单

**Review Report**:
Generate Report Node 生成的最终结构化 JSON 输出，包含 summary、risk 级别和 findings 列表。
_Avoid_: 审查报告、review 结果

**Context Collection**:
Collect Context Node 的执行机制：单次 LLM 调用分析 Diff → 输出需要读取的文件/符号列表 → 批量并行执行 Tool 调用。不采用 ReAct 循环迭代，避免与 Reviewer 分析逻辑重叠。若上下文不足，由 Reflection 触发回退重新收集。
_Avoid_: 上下文获取、按需加载

**Reflection Loop**:
Reflection Node 评估 Findings 后决定是否回退到 Collect Context 的闭环机制。采用硬限制（max 3 轮）+ 软判断（findings 引用具体代码行、已读文件覆盖所有引用、Reviewer confidence 标记）双保险策略，防止无限循环。
_Avoid_: 反思循环、重试机制

**File Context Cache**:
存储在 ReviewState 中的只读文件缓存（file_path → content），由 Collect Context 填充。Reviewer 不直接访问 State，由 Run Reviews Node 根据 Reviewer 声明的 `required_tools` 传递所需文件的子集视图，保证 Reviewer 输入隔离的同时避免重复 I/O。
_Avoid_: 文件缓存、上下文存储

**ReviewState**:
LangGraph Workflow 的全局状态对象。包含：pr 元信息、diff、changed_files、file_context_cache、review_plan、findings、reflection_round、need_more_context、report、tool_calls 审计记录。所有 Node 只读写其职责范围内的字段。

**Planning Trigger**:
Planning Node 选择 Reviewer 的双层策略。软策略：LLM 分析 Diff 自由决定 Review Plan。硬触发器：纯正则规则引擎，基于文件路径/内容模式强制激活特定 Reviewer（如 SQL 关键字 → Security Reviewer）。硬触发器结果与 LLM 输出合并去重，确保关键审查不被遗漏。
_Avoid_: 审查触发条件、Review 策略匹配

**LLM Provider**:
LLM 调用的抽象层。由 `LLMConfig`（Pydantic BaseModel，含 provider/model/temperature/max_tokens）+ 工厂函数创建。基于 LangChain `BaseChatModel` 封装，每个 Node 独立持有实例，支持用户按 Node 单独配置不同的模型和参数。
_Avoid_: LLM 客户端、模型调用、AI 接口

**Tool Registry**:
通过 `@register_tool` 装饰器将 Tool 注册到全局 `TOOL_REGISTRY`，与 Reviewer 的 `@register_reviewer` 模式一致。每个 Tool 声明 name、description 和 execute 方法。Reviewer 通过 `required_tools` 字段引用 Tool name，由 Run Reviews Node 按需注入。
_Avoid_: 工具注册、插件系统

**Reviewer Execution**:
Reviewer 的执行模式：单次 LLM 调用 + Function Calling。LLM 在一次请求中自动决定调用哪些 Tool 并返回 Findings。不采用内部 Agent 循环（ReAct），因为 Reflection Loop 已在外部提供迭代能力。
_Avoid_: Review 执行、审查运行

**Workflow Error**:
Workflow 执行中的错误，按级别分类：可恢复错误（LLM 超时、rate limit，自动重试 2 次，指数退避 + 降级策略）；不可恢复错误（auth 失败、文件缺失，终止并返回 error Report）；部分失败（单个 Reviewer 异常，继续执行，标记空 Findings + error 说明）。统一定义为 `WorkflowError` Pydantic 模型。
_Avoid_: 异常、执行失败

**Static Analysis Tool**:
Ruff、mypy、ESLint 等静态分析工具的封装 Tool。与普通 Tool 一样注册，由 Reviewer 通过 Function Calling 按需调用。Reviewer Prompt 中强制要求"先运行静态分析，再进行人工判断"，确保 LLM 不会跳过工具直接猜测代码问题。
_Avoid_: 代码检查工具、lint 工具

**Review Task**:
一次 Review 请求的异步执行单元。API 收到请求后创建 Task 并立即返回 `review_id`，后台异步运行 LangGraph Workflow。用户通过 `GET /review/{id}` 轮询状态和结果。
_Avoid_: 审查任务、review job

**Local Review**:
针对本地 Git 仓库某次 commit 的审查模式（`POST /review/local`），输入为本地仓库路径 + commit hash。与 GitHub PR Review 共享同一套 Reviewer 和 Workflow，仅 Load PR Node 的数据源不同。
_Avoid_: 本地审查、离线审查

**Prompt Template**:
存储在 `prompts/` 目录下的 Jinja2 模板文件。每个 Reviewer 通过 `prompt_key` 引用对应模板。由 `PromptLoader` 服务统一加载和渲染，Reviewer 不直接读取文件。模板变量包括 diff、files、context、static_analysis_output 等。
_Avoid_: Prompt 文件、提示词模板

**Tool Data Source**:
Tool 的多数据源适配策略。Tool 统一接口（如 `ReadFile`），具体实现按数据源分为 GitHub API 版本和本地 Git 版本。创建 Graph 时根据请求类型（PR vs Local）运行时注入对应的 Tool 实现集合，Reviewer 和 Workflow 不感知底层数据源差异。
_Avoid_: 数据源切换、后端适配
