# Code Reviewer 项目指令

## 基本约束

- 使用中文技术文档风格：正式、书面化、语义完整；避免口语化缩写、过于抽象的表述和模糊简称。
- React/TypeScript、Python 代码中的新增或修改注释使用中文；注释应说明约束、原因或边界，不重复代码表面含义。
- 修改前先阅读相关文件并确认影响范围。涉及审查流程、数据模型、数据库或桌面启动链路时，先阅读对应的设计文档。
- 架构和数据流优先参考 `docs/system-design.md`；审查质量规则参考 `docs/review-quality-gate-implementation-plan.md`；桌面启动和打包参考 `docs/electron-desktop-implementation-plan.md`。
- 需要理解代码时，优先使用 codegraph MCP；工具不可用时，再使用 `rg`、项目入口和测试建立代码上下文。
- 不修改 `node_modules/`、`dist/`、`build/`、`release/` 等依赖或构建产物目录，除非用户明确要求。

## 项目结构与术语

- `backend/`：FastAPI、SQLAlchemy、LangGraph 审查后端；入口在 `backend/app/main.py`，开发环境使用 `backend/.venv/`。
- `frontend/`：React、TypeScript、Vite 前端；页面、组件、API 客户端和类型分别位于 `frontend/src/pages/`、`frontend/src/components/`、`frontend/src/api/` 和 `frontend/src/types/`。
- `desktop/`：Electron 桌面壳，负责启动和管理后端 sidecar，并加载前端资源；源码位于 `desktop/src/`。
- `start.py`：开发启动器；默认同时启动后端和 Vite，`--prod` 模式只启动后端并由后端提供构建后的前端。
- `docs/`：架构、实施方案和设计记录。修改实现时同步检查相关文档是否仍然准确，但不要将未被用户要求的文档扩写为实现计划。

项目统一使用以下术语：

- **Reviewer**：一个 LLM 调用与一组关联 Tool 的绑定体，负责分析 Context 并输出 Finding，不直接执行数据获取。
- **Tool**：单一职责的数据获取或操作单元，不包含 LLM 逻辑，由 Reviewer 或 Workflow Node 调用。
- **Finding**：Reviewer 输出的单个审查发现，包含严重级别、文件、行号、标题、原因和建议。
- **Review Plan**：Planning Node 根据变更内容动态生成的审查计划，决定执行哪些 Reviewer。
- **Review Report**：Generate Report Node 生成的最终结构化结果，包含 summary、risk 和 findings。
- **ReviewState**：LangGraph Workflow 的全局状态对象；各 Node 只读写其职责范围内的字段。
- **FindingGate**：位于候选 Finding 与最终 Review Report 之间的质量门槛，负责检查证据、影响、定位和可执行性。
- **Workflow Error**：Workflow 执行过程中的错误，必须保留错误级别、来源和用户可理解的说明。

## 技术栈与验证

- 前端：React、TypeScript、Vite、Tailwind CSS、shadcn/ui；使用 npm。
- 后端：Python 3.11+、FastAPI、SQLAlchemy、Pydantic、LangGraph；使用 `backend/.venv/` 中的 Python。
- 桌面端：Electron、TypeScript、electron-builder；由 `desktop/` 管理开发启动、sidecar 和 Windows 打包。
- 后端单元测试：在仓库根目录执行：

  `backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -q`

- 后端语法检查：

  `backend\.venv\Scripts\python.exe -m compileall -q backend\app backend\tests`

- 前端质量门禁：在 `frontend/` 中执行 `npm.cmd run build` 和 `npm.cmd run lint`。
- 桌面端质量门禁：在 `desktop/` 中执行 `npm.cmd run build` 和 `npm.cmd test`。
- 变更涉及打包或启动链路时，额外验证 `desktop/` 中的 `npm.cmd run package:win` 或根目录的 `python start.py`；不要把打包产物当作源码变更提交。
- 未通过相关质量门禁的代码不得提交；若环境限制导致某项无法执行，必须在交付说明中明确记录。

## 启动与运行验证

- 开发模式：在仓库根目录执行 `python start.py`，前端默认访问 `http://localhost:5173`，后端默认访问 `http://127.0.0.1:8000`。
- 生产模式：先构建前端，再执行 `python start.py --prod`，由后端提供前端构建产物。
- Electron 开发模式：在 `desktop/` 中执行 `npm.cmd run dev`；它会启动前端开发服务器和 Electron。
- 启动或停止服务前确认端口占用及对应进程；验证结束后关闭本次启动的进程，避免残留后端、Vite 或 Electron 进程。
- 审查过程日志主要写入数据库的 `review_logs` 表，并可通过审查日志 API 查看；Electron sidecar 的标准输出和错误输出由桌面壳收集。排查问题时同时检查 API 日志、审查记录和 sidecar 输出。

## 修改原则

- 后端 Workflow 只负责编排；分类、校验、FindingGate 和报告格式化应保持为可独立测试的模块，避免继续堆积在单个 Workflow 函数中。
- Reviewer 输出首先视为候选 Finding，只有具备变更范围、具体证据、现实影响和可执行建议时才进入最终 Review Report。
- 无法验证的外部事实应记录为检查限制或 `unverified` 状态，不应包装成 Finding。
- 保持 API、Pydantic Schema、前端类型和数据库持久化结构一致；修改响应字段时同时检查历史记录兼容性和详情页展示。
- 前端警示信息按严重程度分层：阻断性错误醒目展示，诊断性信息折叠展示；不要因为普通审查元数据让风险等级或页面主区域显示为错误状态。
- 变更审查输出、归档、Diff 或桌面启动行为时，必须补充对应回归测试或运行验证。

## Git 与文件安全

- 分支名使用 Conventional Commits 类型前缀，例如 `feat/`、`fix/`、`refactor/`、`chore/`；不默认使用 `codex/` 前缀。
- 提交信息使用中文 Conventional Commits，采用祈使语气，格式为 `type(scope): 描述`；主体不超过 72 个字符，正文使用 `- ` 列表。
- 示例：`fix(review): 保留完整的审查输出`、`refactor(stats): 复用归档过滤条件`。
- 不得执行 `git push`；只有在用户检查变更范围并明确同意后才能执行 `git commit`。
- 每次完成修改后，先汇报变更内容并等待用户审查；用户明确说「可以提交」之前不得执行 `git commit`，也不得提前 `git add` 暂存后续可能调整的文件。
- 提交前检查 `git diff --check`、暂存文件列表和暂存差异；在脏工作区中不得把用户已有改动混入本次提交。
- 删除文件、目录或未提交内容前，确认目标路径和影响范围；项目外或批量删除前先列出受影响文件，优先使用可恢复方式。
- 不使用 `git reset --hard` 或 `git checkout --` 覆盖用户改动，除非用户明确要求。
