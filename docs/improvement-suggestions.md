# Code Reviewer 项目改进建议

> 文档状态：分析结论，尚未实施。
> 分析范围：`backend/`（FastAPI + LangGraph 审查引擎）、`frontend/src/`（60 个源文件与配置）、`desktop/src/`（Electron 壳）、`backend/tests`（16 个测试文件）、`docs/` 设计文档。
> 分析时间：2026 年 8 月，基于 `1f9ec2f`（feat(settings): 实现统一设置页只读闭环）之后的工作区快照。

## 一、高优先级（影响正确性或稳定性）

### 1. 后端：service 层反向依赖 API 层，任务执行逻辑放错了位置

- **位置**：`backend/app/services/review_runner.py:104` 导入 `app.api.reviews._run_review_workflow`；`_run_review_workflow`（254 行）与 `_lock_remote_review_revision`（366 行）整个业务执行体都在 `api/reviews.py` 里。
- **问题**：分层倒置——service 依赖 API 模块；418 行的 `api/reviews.py` 混合 HTTP 处理与工作流执行，`review_runner` 无法独立测试（这也是它零测试覆盖的原因之一）。
- **建议**：把 `_run_review_workflow`、`_lock_remote_review_revision` 下沉到 `services/review_runner.py`（或独立的 `services/review_executor.py`），API 层只保留路由与参数校验。与 AGENTS.md「Workflow 只负责编排、模块可独立测试」的原则一致。

### 2. 后端：任务 worker 单进程串行、无并发上限、进程中断丢失审查

- **位置**：`review_runner.py:38-48` 单 worker 循环，`_run_review_workflow` 同步执行完整审查（每次 LLM 调用数分钟）。
- **问题**：① 同一时刻只执行一个审查，多用户同时提交会排队数十分钟；② 无并发上限控制，若改为多 worker 又可能同时打爆 LLM 配额；③ 审查在 API 进程内执行，进程重启/崩溃时正在跑的审查直接丢失（`_recover_running_tasks` 只能恢复已落库的 pending 任务）。
- **建议**：worker 侧引入有上限的并发领取（如 `asyncio.Semaphore(2)` 控制同时在跑的审查数）；为每个 task 增加超时/取消机制；文档已声明「claim 接缝可替换为外部队列」，可先落地并发与超时，外部队列保持为演进方向。

### 3. 后端：ReviewTaskRunner.stop() 无超时，进程退出可能挂起

- **位置**：`review_runner.py:31-36`，`lifespan` 的 finally 中 `await runner.stop()`（`main.py:38`）。
- **问题**：stop 等待当前审查自然结束，一次审查可能长达数十分钟（多轮 LLM 调用），Ctrl+C 或 `start.py` 退出时 uvicorn 会长时间无法关闭。
- **建议**：stop 时给 `_worker` 等待加超时（如 5 秒），超时后直接返回；未完成的任务靠启动时的 running→pending 恢复机制兜底。

### 4. 后端：数据库无迁移工具，`ensure_schema()` 只对 SQLite 生效

- **位置**：`models/base.py:46-84`。
- **问题**：手写 `ALTER TABLE` 补丁在 PostgreSQL（文档声明生产环境使用）下直接 no-op，新增字段无人维护；且 `table_additions` 会随代码无限膨胀。
- **建议**：引入 Alembic 管理迁移（PostgreSQL 走正式迁移，SQLite 保留 `ensure_schema` 兼容已有库文件）；或至少在 `ensure_schema` 中为 PostgreSQL 增加等价补丁。

### 5. 后端：CRG 图谱永不过期，影响半径可能基于过期数据

- **位置**：`engine/crg.py:32-38`，仅当 `.code-review-graph/` 不存在时构建。
- **问题**：仓库持续推进后，后续审查仍使用首次构建的旧图谱，「受影响文件」候选与 impact_radius 失真，还会误导「追加 security reviewer」的硬触发。
- **建议**：以仓库最近同步时间或 HEAD revision 为指纹，变化时重建图谱（`build_or_update_graph` 本身支持增量）。

### 6. 前端：ReviewDetail 轮询无防重入与卸载守卫，终止判定依赖日志文案

- **位置**：`frontend/src/pages/ReviewDetail.tsx:173-177`（`setInterval(fetchAll, 2000)`）、:142-148（`l.message === "审查完成"`）；`ReviewProgress.tsx:83-85` 同样依赖文案。
- **问题**：① 单次请求超过 2 秒时并发请求堆积，响应顺序无保证；② 卸载后进行中的请求仍 setState；③ 轮询终止靠硬编码日志文案，后端改文案即失效。
- **建议**：抽取通用 `usePolling(fetcher, { interval, shouldStop })` hook（内置 in-flight 互斥、卸载取消、active 守卫，参照 `use-settings.ts:30-63` 的写法）；终止判定改用 `task.status` 字段，日志文案仅作展示。

### 7. 前端：死代码 `lib/error-message.ts` 与 `utils/error-message.ts` 重复

- **位置**：`frontend/src/lib/error-message.ts`（28 行，全项目无引用，已 grep 确认）与 `utils/error-message.ts`（116 行，实际使用）。
- **问题**：两版 `formatErrorMessage` 逻辑不一致——lib 版有 401/authentication 分支，utils 版缺失。
- **建议**：删除 `lib/error-message.ts`，把 401 分支并入 utils 版并补单测。

### 8. 前端：tsconfig 未开启 `strict`

- **位置**：`frontend/tsconfig.app.json:2-31`。
- **问题**：`strict`、`strictNullChecks`、`noUncheckedIndexedAccess` 全部关闭，`null/undefined` 与隐式 any 检查缺失，类型系统形同虚设。
- **建议**：开启 `"strict": true`（可加 `noUncheckedIndexedAccess`），借助 `npm run build`（已含 `tsc -b`）逐步清理存量。

### 9. 桌面：sidecar 就绪后崩溃，状态泄漏且无自动重启

- **位置**：`desktop/src/sidecar-manager.ts:176-184`（exit 处理仅 `status !== "ready"` 时置 failed）、:60-63（start 短路复用）。
- **问题**：进程就绪后崩溃，状态永远停留在 `ready`、`baseUrl` 失效，`start()` 直接短路返回死地址，渲染进程持续请求已死的 sidecar，且无重启机制。
- **建议**：exit 处理器统一置 `failed` 并清空 `child/baseUrl`；对就绪后崩溃增加带退避的自动重启，或至少让 `start()` 复用前重新探活 `/api/ready`。

### 10. 测试覆盖的关键缺口（后端）

- **`engine/crg.py`（高）**：所有测试仅 mock `try_crg_context`，真实实现的成功路径与 ImportError/构建失败/status 非 ok 四条降级路径零覆盖。
- **`services/review_runner.py`（高）**：`_claim_next_task` 原子更新（`updated != 1` 回滚）、running→pending 恢复、worker 启停生命周期零覆盖——这正是第 1、2 条建议的改动区域，必须先有测试保护。
- **`engine/reviewers/security.py`、`performance.py`（高）**：只有 StyleReviewer 有测试；security reviewer 会被 CRG 高影响动态追加，属高风险路径。
- **中优先级缺口**：`api/stats.py`、`engine/tools/*`、`services/settings_service.py`、`engine/prompt/prompt_builder.py`。

## 二、中优先级（结构性改进）

### 后端

11. **LLM 配置死字段**：`config.py:24` 有 `llm_provider`，但 `engine/llm.py:18-22` 固定用 `deepseek_api_key` 构造 OpenAI client，provider 字段无人消费。要么实现 provider→(base_url, key) 映射，要么删除该字段。
12. **`engine/llm.py` 重复代码**：`chat_with_tools` 与 `_finalize_json` 的「最终 JSON 收口 prompt」「空响应重试」逻辑重复两遍，建议提取公共 helper。
13. **错误语义靠字符串匹配**：`engine/errors.py:11-21` 与前端 `utils/error-message.ts:34-55` 各自基于供应商错误文案匹配 401/429/余额，供应商改文案即失效。建议后端抛出结构化错误（code + message），前端只翻译 code。
14. **stats API 全量内存聚合 + SQLite 方言**：`api/stats.py:41-49` 把全部 report 行拉到 Python 计算风险分布，热力图同理（:128-140）；`func.strftime`（:138）在 PostgreSQL 不可用。建议 GROUP BY 聚合 + 方言适配；顺带清理 `stats.py:16` 的重复导入。
15. **`api/repos.py:87-93` 同步 clone**：`subprocess.run` 120 秒阻塞线程池，无并发限制，多个大仓库同时 clone 会占满线程池；建议改为后台任务或加并发信号量。
16. **前端类型与后端 schema 漂移**：`src/types/*.ts` 手写类型与 Pydantic 无关联，且大量 `| string` 兜底（`types/index.ts:8,18,28,44` 等）使联合类型退化为 string。建议用 openapi-typescript 从后端 OpenAPI 生成类型。

### 桌面

17. **spawn error 时 `stop()` 空等 3 秒**（`sidecar-manager.ts:112-119`）：error 事件不触发 exit，等待只能靠超时兜底，随后对已死进程发 SIGKILL。应在 error 回调中统一 resolve 终止信号。
18. **端口分配 TOCTOU 竞态**（`sidecar-manager.ts:21-37`）：监听 0 端口→关闭→复用端口，窗口期可能被抢占；生产模式端口冲突不重试。建议后端监听成功后回报实际端口。
19. **`desktop:open-path` 无路径白名单**（`desktop-bridge.ts:30-36`）：渲染进程可触发打开任意路径；当前无消费方，建议限定在 dataDir/仓库目录内或直接移除。
20. **缺导航拦截**（`main.ts:79-96`）：无 `will-navigate`/`setWindowOpenHandler`，页面若被导航到外部站点，将与「127.0.0.1 无鉴权后端 + CORS 放行」组合成攻击面。建议仅放行自身 origin。
21. **electron-builder 配置缺失**（`desktop/package.json:25-53`）：无图标、无签名（SmartScreen 警告）、未收敛 `electronLanguages`；`shadcn`（CLI）误放 `frontend` 的 dependencies。

## 三、低优先级（清理与一致性）

22. **文档漂移**：`docs/system-design.md` 的项目结构（`models/review.py`、`services/review_service.py`、`NewReview.tsx`、`usePolling.ts` 等）与实现不符；`CONTEXT.md` 描述的 `@register_reviewer` 装饰器、Tool 多数据源注入、`WorkflowError` Pydantic 模型均未实现。建议按当前结构更新，或在 ADR 记录演进，否则新成员会按旧文档写代码。
23. **前端死代码**：`components/ui/collapsible.tsx`（带 Next.js `"use client"` 遗留，全项目无引用）；`ReviewHeatmap.tsx:50` 的 `repo.cells.find` 可改 Map 预建。
24. **标签函数重复 2~4 份**：`sourceLabel` 在 ReviewDetail/RepoDetail/ChangeDiffViewer/ReviewHeader 各一份，`statusLabel` 三份——建议集中到 `src/lib/labels.ts`。
25. **前端 loading/error 样板重复**：Dashboard/RepoDetail/RepoList 等 6 个页面手写 `useState + toUserError + finally`，建议抽 `useAsync` hook。
26. **sidecar 日志无落盘**（`sidecar-manager.ts:211-214`）：按 chunk 截断且只进 console，建议按行缓冲并写入 userData 日志文件。
27. **桌面测试单薄**：仅 1 条 happy-path 用例（`sidecar-manager.test.ts`），就绪超时、就绪后崩溃、SIGKILL 升级、spawn error 等全缺；main/preload/bridge 零测试。SidecarManager 的依赖注入设计已具备可测性，补测成本低。

## 四、建议的落地顺序

1. **先修正确性**：sidecar 崩溃状态泄漏（9）、轮询竞态与终止判定（6）、worker 停止超时（3）、ReviewDetail 拆分（664 行含 6 个分支状态机）。
2. **再补测试护栏**：`review_runner`、`crg`、security/performance reviewers 的后端测试（10）；前端 `parseDiff`、轮询、审查提交单测。
3. **然后做架构收敛**：任务执行下沉到 service（1）、并发领取（2）、Alembic 迁移（4）、strict 开启（8）。
4. **最后清理**：死代码（7、23）、文档漂移（22）、依赖治理（21）、CRG 图谱刷新（5）、stats 聚合（14）。
