# Code Reviewer 统一设置页面实施方案

- 文档状态：实施方案与当前状态
- 编制日期：2026-08-13
- 适用范围：E:/code-reviewer
- 首批实施范围：统一设置页、配置持久化和安全凭据闭环

> 当前实现状态（2026-08-26）：设置页已进入可用配置阶段。非敏感设置通过
> `PATCH /api/settings` 保存到版本化 `settings.json`；模型连接可测试；Electron
> 使用 `safeStorage` 管理模型和代码托管凭据，并在 sidecar 重启时注入。本文中
> “P0/P1/P1.5”仅用于说明实施批次，不得直接复制到用户界面文案。

## 1. 方案结论

当前应用通过 /settings 页面提供本机工作区的设置中心，统一查看外观、模型服务、代码托管、审查行为、提示词工作台、数据目录和运行诊断。非敏感配置支持显式保存和版本冲突检查；模型连接支持使用当前配置或页面草稿测试；Electron 模式支持通过受控桌面桥接管理安全凭据，并在 sidecar 重启时注入。

设置能力分为三层：

1. 前端本地偏好：主题等立即生效的界面偏好。
2. 本机工作区配置：模型参数、审查参数、提示词限制和仓库根目录。
3. 启动级运行配置与安全凭据：数据库、sidecar、API Key、GitHub/Gitee Token 等需要特殊权限或重启边界的内容。

设置页不直接把后端 Settings 类的所有字段渲染成表单。后端部署参数、桌面启动参数和用户可调参数需要保持明确边界；只有存在真实运行时消费者、已定义生效时机并能被测试验证的字段，才进入可编辑设置模型。敏感凭据由 Electron 主进程拥有安全存储，sidecar 只在受控启动链路中获得有效凭据。

本修订方案固定以下实现前提：

1. 非敏感用户配置使用版本化 JSON 文件持久化，不新增设置 ORM 表。Electron 模式写入 `%APPDATA%/Code Reviewer/data/settings.json`；浏览器模式使用后端数据目录下的 `settings.json`，但不提供敏感凭据写入能力。
2. 配置优先级从低到高为：代码默认值、`.env`/进程环境、用户配置文件；sidecar 通过命令行传入的数据目录和静态资源路径属于 RuntimeSettings，不受用户配置文件覆盖。临时测试草稿只对测试请求生效，不写入持久化配置。
3. 配置文件使用临时文件写入后原子替换，并包含 `schema_version`。读取失败、校验失败或替换失败时保留上一份有效配置，不产生半保存状态。
4. ReviewTask 在被 worker 领取时生成有效配置快照。已运行审查继续使用原快照，新任务使用保存后的新配置，避免审查过程中途切换模型、反思轮数或上下文策略。
5. 当前实现已覆盖非敏感配置持久化、运行时刷新、模型连接测试以及 Electron 模式的 safeStorage 凭据传递；浏览器模式的 `.env` 凭据保持只读说明，不通过网页持久化。P0/P1/P1.5 仅作为历史实施批次记录，不代表当前页面能力。

本文记录设置功能的实现边界、接口、交互、数据流和验收标准，并在后续代码变更时同步维护当前实现状态。

## 2. 当前实现基线

### 2.1 前端现状

当前路由包含仪表盘、仓库列表、仓库详情、审查详情和提示词工作台，没有 /settings 路由。导航入口位于 frontend/src/components/Layout.tsx，主题状态由 frontend/src/hooks/use-theme.ts 读取和写入 localStorage。

当前已经具备以下可复用基础：

- React Router、Tailwind CSS、Geist 字体和现有主题 Token；
- Button、Card、Modal、Table、Skeleton 等 UI 基础组件；
- 统一错误信息转换函数 frontend/src/utils/error-message.ts；
- Electron 运行时信息读取和目录选择能力；
- 提示词工作台使用的表单、加载、错误和会话状态模式。

主题当前可以立即切换，但没有页面入口。设置页需要把现有能力显式化，并沿用当前控制台风格，避免引入独立的视觉系统。

### 2.2 后端现状

backend/app/config.py 当前同时包含以下配置：

- 数据库路径、仓库存储路径和前端静态文件路径；
- 反思轮数、Reviewer 超时、上下文文件数和 CRG 开关；
- 提示词请求、输入、输出和会话限制；
- LLM 服务类型、模型、Temperature、最大 Token、API Key 和 Base URL；
- GitHub 与 Gitee Token；
- CORS 配置。

当前配置通过 pydantic-settings 从 .env 加载，`settings = Settings()` 在模块导入时创建。应用没有设置读取 API、设置保存 API、凭据清除 API 或连接测试 API。

当前代码与设置字段之间还存在需要在 P1 前处理的差异：

- `max_reflection_rounds`、`context_files_per_round` 在 Workflow Node 中被读取；`repos_dir` 在新仓库创建时被读取；
- `reviewer_timeout_seconds` 和 `llm_provider` 目前只有配置声明，没有实际消费者，不能直接作为“已可调配置”展示；
- `crg_enabled` 目前不是由 `settings.crg_enabled` 控制，Workflow 初始值为 `True`，上下文收集阶段再根据 CRG 调用结果改写状态；
- PromptOptimizer 是 API 模块级对象，其 PromptSessionStore 在构造时固定 TTL、容量和上下文长度，更新配置不会自动改变既有会话仓库；
- LLMProvider 在首次使用时创建全局单例，并将 API Key、Base URL、模型和调用参数缓存到实例中。

因此 P1 必须先建立“配置字段—真实消费者—生效时机—验证用例”清单。页面不能把未接入运行时的字段包装成已生效的设置。

### 2.3 Electron 现状

Electron 主进程已经提供：

- get-info：运行模式、API 地址、数据目录和版本；
- choose-directory：选择目录；
- open-path：使用系统能力打开目录或文件；
- sidecar 状态转发。

前端运行时类型还没有完整暴露所有已存在的桥接能力：preload 已实现 `openPath()` 和 `onBackendState()`，但 `frontend/src/runtime/desktop.ts` 尚未把它们完整声明给 Renderer。设置页需要补齐类型和运行时适配器；P1.5 再增加 safeStorage 相关白名单，同时保持 `contextIsolation`、`sandbox` 和 `nodeIntegration: false` 的安全边界。

## 3. 目标信息架构

设置页使用单一路由和页面内二级导航。桌面端为“左侧分区导航 + 右侧设置表单”，窄屏改为顶部选择器或可折叠分区列表。

| 设置分区 | 内容 | 生效方式 | 优先级 |
|---|---|---|---|
| 常规与外观 | 跟随系统、浅色、深色 | 立即生效 | P0 |
| 模型服务 | 当前 OpenAI 兼容服务、模型、Base URL、凭据状态、Temperature、最大输出 Token | 新任务使用配置快照；凭据需要重启 sidecar | P0 只读，P1 编辑 |
| 代码托管 | GitHub、Gitee 配置状态和连接状态 | 连接测试使用当前有效凭据；凭据需要重启 sidecar | P0 只读，P1.5 编辑 |
| 审查行为 | 最大反思轮数、上下文文件数、CRG 策略；Reviewer 超时需先完成运行时接入 | 新任务使用配置快照 | P1 |
| 提示词工作台 | 请求超时、最小/最大输入长度、输出 Token、会话 TTL、会话数量和上下文限制 | 新会话或新请求按配置生效 | P1 |
| 数据与诊断 | 数据目录、仓库根目录、sidecar 状态、版本、打开目录 | 按操作类型生效 | P0 |
| 关于 | 应用版本、运行模式、API 地址、诊断信息 | 只读 | P0 |

以下配置保留为内部或部署配置，不进入普通设置页面：

- database_url；
- frontend_dist_dir；
- cors_origins；
- review_worker_poll_seconds；
- Electron 可执行文件、sidecar 端口和启动参数；
- 数据库迁移、清理和内部日志配置。

repos_dir 可以在桌面端呈现为“仓库根目录”。修改后只影响新创建或重新同步的仓库，不自动搬迁既有仓库。

`database_url`、`frontend_dist_dir`、`cors_origins` 和 `review_worker_poll_seconds` 不进入 UserSettings。它们属于启动或部署配置，变更需要重启或重新启动方式，不由设置页伪装成热更新设置。`repos_dir` 是唯一需要明确允许外部路径的用户配置：必须是绝对、规范化且可写或可创建的目录；它可以位于用户数据目录之外，但不会自动移动既有仓库，也不能与数据库、配置和日志目录重合。

## 4. 页面与交互设计

### 4.1 页面结构

~~~text
设置                                      本机工作区 · 桌面版
管理模型、审查、仓库连接和本地数据

常规与外观       外观
模型服务         主题
代码托管         ○ 跟随系统  ○ 浅色  ○ 深色
审查行为
提示词工作台     模型服务
数据与诊断       当前配置状态、模型、Base URL
关于             API Key：已配置
                                            [保存本节]
~~~

### 4.2 表单规则

- 每个设置分区独立保存，避免单个字段验证失败阻断整页。
- 主题切换立即生效并写入本地偏好。
- 模型、凭据和路径配置采用显式保存，不使用隐式自动保存。
- 页面顶部显示“有未保存更改”状态。
- 保存期间禁用当前分区操作并显示进行中状态。
- 保存成功后显示保存结果和生效范围，例如“对新审查生效”或“重启后生效”。
- 失败信息显示在对应字段附近，并提供重试、修复或检查服务入口。
- 高级配置默认折叠，常用配置保持首屏可见。
- API Key 和 Token 只显示“已配置/未配置”，不回显完整值。
- 表单字段使用可见 label、辅助说明、键盘焦点样式和 aria-describedby。
- 375px 宽度下使用单栏布局，避免多个嵌套滚动区域。
- 设置分区导航支持键盘操作，当前分区具有明确的选中状态。

### 4.3 浏览器与 Electron 差异

页面根据运行时能力显示不同状态：

- Electron 模式：支持选择目录、打开数据目录、读取 sidecar 状态和后续安全凭据保存。
- 浏览器模式：显示服务端运行模式和配置来源；目录选择、打开本地路径和安全凭据保存显示为受限能力。
- 页面不能把浏览器模式下不可用的桌面按钮显示为可操作状态。

## 5. 配置分层与数据模型

建议将当前单一配置对象拆分为三个概念模型。

### 5.1 RuntimeSettings

用于应用启动和部署，不提供普通用户编辑：

~~~text
database_url
frontend_dist_dir
cors_origins
review_worker_poll_seconds
sidecar host/port
settings_file
~~~

### 5.2 UserSettings

用于本机工作区的可调配置：

~~~text
llm.model
llm.base_url
llm.temperature
llm.max_tokens
review.max_reflection_rounds
review.context_files_per_round
review.crg_enabled
prompt.timeout_seconds
prompt.min_input_chars
prompt.max_input_chars
prompt.max_output_tokens
prompt.session_ttl_seconds
prompt.session_max_count
prompt.session_max_context_chars
storage.repos_dir
~~~

`review.reviewer_timeout_seconds` 暂不进入 UserSettings，直到审查执行路径实际使用该值并有超时回归测试。`llm.provider` 只作为当前实现的只读能力标识，第一阶段固定为 `deepseek-openai-compatible`，不宣称已经具备原生多供应商切换能力。

### 5.3 SecretSettings

用于 API Key 和代码托管 Token：

~~~text
llm.api_key                 # 当前映射到 deepseek_api_key
github.token
gitee.token
~~~

敏感值不进入普通设置响应。响应只包含配置状态，例如：

~~~json
{
  "api_key_configured": true,
  "github_token_configured": false
}
~~~

当前 LLM 实现实际使用 DeepSeek 的 OpenAI 兼容接口。规范化设置名与现有字段的映射必须固定：`llm.api_key -> deepseek_api_key`，`llm.base_url -> deepseek_base_url`，`llm.model -> llm_model`。第一阶段界面应使用“OpenAI 兼容模型服务”或“当前模型服务”这类准确表述，暂不展示尚未实现的原生多供应商能力。

### 5.4 有效配置快照

后端对外返回的不是原始 `Settings` 对象，而是脱敏的 `EffectiveSettingsSnapshot`：

~~~json
{
  "schema_version": 1,
  "config_version": 3,
  "sources": {
    "llm.model": "user_file",
    "llm.base_url": "env",
    "review.max_reflection_rounds": "default"
  },
  "settings": {
    "llm": {
      "provider": "deepseek-openai-compatible",
      "model": "deepseek-chat",
      "base_url": "https://api.deepseek.com/v1",
      "temperature": 0.1,
      "max_tokens": 4096
    }
  },
  "secret_status": {
    "llm_api_key": "configured",
    "github_token": "not_configured",
    "gitee_token": "not_configured"
  }
}
~~~

`sources` 只返回来源类别，不返回环境变量名、文件内容或凭据位置。`config_version` 用于防止并发保存覆盖较新的配置；PATCH 可携带 `expected_version`，版本不匹配时返回冲突而不是静默覆盖。

## 6. API 与数据流

### 6.1 API 设计

P0/P1 后端 API 只负责非敏感设置读取、非敏感配置保存和使用当前有效凭据的连接测试。凭据保存与清除由 P1.5 的 Electron 主进程接口负责，避免把 safeStorage 的所有权错误地放在 FastAPI 普通设置 API 中。

建议新增以下接口：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | /api/settings | 返回脱敏后的有效配置快照 |
| PATCH | /api/settings | 更新非敏感配置 |
| POST | /api/settings/test/llm | 使用当前有效凭据测试模型服务 |
| POST | /api/settings/test/git/{provider} | 使用当前有效凭据测试 Git 主机 API |

`PATCH /api/settings` 请求体只允许 UserSettings 中已经接入真实消费者的字段，并支持部分更新：

~~~json
{
  "expected_version": 3,
  "settings": {
    "llm": {
      "model": "deepseek-chat",
      "temperature": 0.1,
      "max_tokens": 4096
    },
    "review": {
      "max_reflection_rounds": 3,
      "context_files_per_round": 20,
      "crg_enabled": true
    }
  }
}
~~~

`expected_version` 缺失时只允许在没有并发保存风险的本地单用户初始化场景使用；正常保存必须携带版本号。请求未知字段、只读字段、部署字段或尚未接入运行时的字段时返回稳定错误码，不静默忽略。

PATCH 响应需要返回逐字段生效范围：

~~~json
{
  "status": "saved",
  "config_version": 4,
  "changed": [
    {"path": "llm.model", "effective_for": "new_reviews", "requires_restart": false},
    {"path": "review.max_reflection_rounds", "effective_for": "new_reviews", "requires_restart": false}
  ]
}
~~~

连接测试请求只允许提交非敏感草稿，例如模型名、Base URL 和参数；API Key、GitHub Token 和 Gitee Token 从当前有效凭据来源取得，不进入浏览器请求体。`test/git/{provider}` 的 provider 只允许 `github` 或 `gitee`，测试目标为对应平台的当前用户或令牌校验 API，不记录完整请求 URL、请求头和异常响应原文。

### 6.2 设置读取流程

~~~mermaid
flowchart LR
    A[Settings 页面] --> B[GET /api/settings]
    A --> C[getDesktopRuntime]
    B --> D[EffectiveSettingsSnapshot]
    C --> E[运行模式、版本、数据目录、sidecar 状态]
    D --> F[脱敏合并展示]
    E --> F
    F --> G[按分区编辑和保存]
~~~

页面需要合并三类状态：

1. 前端本地偏好，例如主题；
2. 后端有效配置，例如模型和审查参数；
3. Electron 运行时信息，例如版本、数据目录和 sidecar 状态。

### 6.3 配置保存流程

非敏感配置保存流程：

~~~text
表单草稿
  -> 字段校验
  -> PATCH /api/settings（携带 expected_version）
  -> SettingsPolicy 校验字段、依赖和路径
  -> SettingsStore 临时文件写入并原子替换
  -> EffectiveSettingsRuntime 更新新任务使用的配置
  -> 返回逐字段 changed / requires_restart / effective_for
  -> 页面展示保存结果
~~~

敏感凭据保存流程：

- Renderer 通过受限 preload 调用 `saveSecret(provider, value)`，Electron 主进程确认 `safeStorage.isEncryptionAvailable()` 后写入安全存储；
- Renderer 和普通设置 API 不长期保存或回显 API Key、GitHub Token、Gitee Token；
- sidecar 重启前由主进程从 safeStorage 读取凭据，并通过不出现在命令行、URL 或日志中的受控进程环境注入给 sidecar；
- sidecar 只在启动时读取凭据，重启流程必须经过 `starting -> ready` 或 `failed` 状态闭环；
- 保存、清除和测试操作均显示明确反馈，失败时不删除旧凭据；
- 浏览器模式显示 .env 配置说明，不在浏览器中持久化敏感凭据。

如果目标环境不允许通过进程环境传递凭据，则必须在 P1.5 开始前替换为受保护的本机进程间通道；不得把凭据作为命令行参数传递。

## 7. 文件变更规划

### 7.1 前端

新增：

~~~text
frontend/src/pages/Settings.tsx
frontend/src/api/settings.ts
frontend/src/types/settings.ts
frontend/src/hooks/use-settings.ts

frontend/src/components/settings/
├── SettingsNavigation.tsx
├── AppearanceSettings.tsx
├── ModelSettings.tsx
├── GitHostSettings.tsx
├── ReviewSettings.tsx
├── PromptSettings.tsx
├── StorageSettings.tsx
├── RuntimeStatusCard.tsx
└── SecretField.tsx
~~~

修改：

~~~text
frontend/src/App.tsx
frontend/src/components/Layout.tsx
frontend/src/runtime/desktop.ts
~~~

### 7.2 后端

新增：

~~~text
backend/app/api/settings.py
backend/app/services/settings_store.py
backend/app/services/settings_policy.py
backend/app/services/settings_service.py
backend/app/services/settings_runtime.py
backend/app/services/settings_connection_test.py
backend/tests/test_settings_api.py
backend/tests/test_settings_store.py
backend/tests/test_settings_service.py
backend/tests/test_settings_runtime.py
~~~

本方案不新增设置 ORM 模型。`settings_store.py` 使用版本化 JSON 文件、临时文件和原子替换；设置文件路径由 RuntimeSettings 提供，默认位于数据目录。SQLite 继续只保存仓库、审查任务和报告，不混入部署配置、用户配置和凭据。

`settings_store.py` 负责：

- 读取 `settings.json` 并校验 `schema_version`；
- 临时文件写入、原子替换和配置版本递增；
- 文件损坏、权限不足和并发版本冲突处理；
- 保存失败时保留上一份有效配置。

`settings_service.py` 作为设置模块的协调接口，负责：

- 按固定优先级解析默认值、`.env`/进程环境和用户配置文件；
- 返回脱敏的 EffectiveSettingsSnapshot、来源和 secret status；
- 调用 SettingsPolicy 执行字段范围、依赖关系和路径校验；
- 返回逐字段生效范围、版本和重启要求；
- 拒绝部署字段、只读字段和未接入实际消费者的字段。

`settings_runtime.py` 负责将配置应用到运行对象：

- ReviewTask 领取时生成不可变配置快照；
- 新建 LLMProvider 或使用配置版本刷新 LLM 客户端；
- 让 PromptOptimizer 的会话限制在新会话创建时使用最新配置；
- 明确当前任务、已有 Prompt 会话和 sidecar 重启之间的生效边界。

`settings_connection_test.py` 只负责 LLM/Git 主机探测，不负责配置持久化；测试器接收已解析的非敏感草稿和凭据适配器，禁止把请求头、完整 URL 或完整异常写入日志。

实现设置 API 时必须修改并纳入变更范围：

~~~text
backend/app/main.py                  # 注册 settings router
backend/app/config.py                # 接入 RuntimeSettings 和有效配置加载
backend/app/engine/llm.py            # 消除全局缓存不刷新或改为配置快照
backend/app/services/prompt_optimizer.py # 让新会话使用最新会话限制
backend/app/services/git_host.py     # 使用新的有效凭据来源
backend/app/engine/workflow.py       # 注入 ReviewTask 配置快照和 CRG 策略
backend/app/engine/nodes/collect_context.py # 使用配置快照控制上下文和 CRG
backend/app/engine/nodes/reflection.py      # 使用配置快照控制反思轮数
backend/app/engine/nodes/run_reviews.py     # 若启用 Reviewer 超时，接入实际执行路径
~~~

### 7.3 Electron

需要检查和扩展：

~~~text
desktop/src/desktop-bridge.ts
desktop/src/preload.ts
desktop/src/types.ts
desktop/src/channels.ts
desktop/src/main.ts
desktop/src/sidecar-manager.ts
~~~

P1.5 新增：

~~~text
desktop/src/secret-store.ts
~~~

可能增加的最小桥接能力：

~~~text
getInfo()
chooseDirectory()
openPath()
onBackendState()
~~~

P1.5 再增加：

~~~text
saveSecret(provider, value)
clearSecret(provider)
restartBackend()
onSecretState()
~~~

`saveSecret` 和 `clearSecret` 的 provider 只允许 `llm`、`github`、`gitee`。Renderer 不获得 Node.js、文件系统、safeStorage 或任意 IPC 能力；`restartBackend()` 只能由主进程调用 SidecarManager，不能由页面自行拼接进程命令。

所有桥接能力必须经过 preload 白名单暴露。Renderer 不获得 Node.js、文件系统或任意 IPC 能力。

## 8. 分阶段实施

### P0：统一设置页与安全只读闭环

目标：让用户能够找到设置、查看当前配置、管理外观和确认运行状态。

范围：

- 冻结 SettingsSnapshot、配置来源、secret status、运行时能力和错误码契约；
- 实现 GET /api/settings，并在 backend/app/main.py 注册 settings router；
- 新增 /settings 路由和桌面、移动端导航入口；
- 实现设置页布局、二级导航和响应式适配；
- 接入现有主题切换能力；
- 展示模型、Git 主机、运行模式、版本、数据目录和配置来源；
- 展示后端状态、API 地址和数据目录打开入口；
- 增加空状态、加载失败和重试状态；
- API Key/Token 只展示配置状态；
- 不在此阶段写入后端配置、敏感凭据或启动参数；主题仍可写入前端 localStorage，不增加 safeStorage 或 sidecar 重启；
- 浏览器模式和 Electron 模式的不可用能力必须通过 capability 显式标识。

P0 不包含 PATCH、连接测试、凭据清除、sidecar 重启或配置文件写入。P0 的完成结果是“可安全读取和展示”，不是“设置已经可编辑”。

### P1：非敏感配置编辑与连接验证

范围：

- 固定 settings.json 的路径、版本、原子写入、恢复和并发版本冲突行为；
- 保存模型参数、审查参数、提示词限制和仓库根目录；
- 增加字段级校验和关联校验；
- 增加模型服务测试与 Git 主机测试；
- 返回配置生效范围；
- 接入统一错误映射；
- 让新 ReviewTask 在领取时读取配置快照；
- 让新 Prompt 会话使用最新会话限制，已有会话保留创建时契约；
- 为全局 LLM 客户端增加刷新或配置版本机制；
- 在 Reviewer 超时真正接入执行路径并补充测试前，不在页面显示 `reviewer_timeout_seconds`。

P1 不保存 API Key 或 Git Token。连接测试只能使用当前有效凭据；表单中的敏感字段不通过浏览器请求体传递。

### P1.5：安全凭据管理与 sidecar 重启

范围：

- 集成 Electron safeStorage；
- 实现 API Key、GitHub Token 和 Gitee Token 的保存、清除和状态查询；
- 定义 safeStorage 到 sidecar 的凭据传递方式，验证凭据不出现在命令行、URL、普通环境诊断和日志中；
- 实现 sidecar 重启和重新就绪流程；
- 增加重启中、重启失败和恢复入口；
- 验证凭据不会进入普通日志、审查日志或 URL；
- 浏览器模式保留 .env 配置说明。

P1.5 的凭据保存和清除操作由 Electron 主进程完成。浏览器模式只能展示 `.env` 配置说明和配置状态，不能伪造可操作的保存或清除按钮。

### P2：数据维护与高级设置

范围：

- 仓库根目录变更前的可写性检查；
- 数据目录备份和恢复入口；
- 非敏感配置导出与导入；
- 审查历史清理前的二次确认；
- 日志目录打开和诊断包导出；
- 账号、多用户、云端同步等能力另行建模。

## 9. 关键风险与处理原则

### 9.1 配置加载时机

当前后端配置在模块导入时初始化。修订后的加载顺序为：RuntimeSettings 先解析数据目录和 settings 文件路径，SettingsStore 再加载用户配置，最后由 EffectiveSettingsResolver 合并默认值、`.env`/进程环境和用户配置。数据库 Engine、静态前端目录和 sidecar 启动参数仍属于启动级配置。

设置服务必须明确：

- 哪些配置在请求时只读取当前有效快照；
- 哪些配置在 ReviewTask 领取时固化为任务快照；
- 哪些配置在新 Prompt 会话创建时读取；
- 哪些配置需要重启 sidecar；
- 页面如何展示“已保存但尚未生效”。

任何修改 `database_url`、`frontend_dist_dir`、sidecar 参数或进程环境凭据的能力都必须返回 `requires_restart=true`，并且不能通过 PATCH 伪装成当前进程已经完成热更新。

### 9.2 LLM 客户端缓存

当前 LLM Provider 是全局单例。设置保存后必须刷新客户端或让新 ReviewTask 创建带有配置版本的 Provider；不能仅更新页面展示值。刷新和任务快照必须覆盖模型、Base URL、Temperature、最大 Token 和凭据来源，并为当前审查仍使用旧配置提供可解释状态。

PromptOptimizer 和 PromptSessionStore 也属于配置消费者。会话 TTL、容量和上下文限制不能只写入启动时的构造参数；至少要定义“新会话使用新值、旧会话保持旧值”的规则，并增加对应测试。

### 9.3 凭据安全

- 不在 GET 响应中回传完整密钥；
- 不把密钥写入 SQLite、仓库目录、命令行参数、URL 或普通日志；
- 清除凭据使用独立操作和确认流程；
- 连接测试不记录请求头和完整异常内容；
- 设置 API 只面向本机单用户和回环地址开放，启动链路必须拒绝非回环绑定；
- P1.5 的凭据保存、清除、读取和 sidecar 重启必须由主进程白名单 IPC 完成，Renderer 不直接接触 safeStorage；
- 诊断信息只返回凭据是否配置，不返回凭据来源的文件名、环境变量名或进程环境内容。

### 9.4 数据目录变更

修改仓库根目录不自动移动既有仓库。`repos_dir` 必须转换为绝对、规范化路径，检查目标是否可写或可创建，并拒绝与数据库、配置或日志目录重合。页面需要显示目标目录、影响范围、可写性检查结果和失败恢复路径。既有 `Repo.local_path` 保持不变，新建或重新同步的仓库才使用新目录。

### 9.5 浏览器与 Electron 能力差异

Electron 可以选择目录、打开路径和使用安全存储。浏览器模式应显示能力限制，禁止把不可用能力伪装为可操作按钮。

### 9.6 当前工作区边界

当前仓库存在多处未提交的前端、后端、测试和文档改动。实施设置页前应重新执行 `git status --short` 和目标文件差异快照，记录初始状态。实现时只允许修改本功能清单内的新增文件和明确列出的既有文件；完成后应使用初始清单排除既有改动，并验证设置功能的新差异没有混入其他 UI 改动。`docs/system-design.md` 需要在实现完成后同步补充 `/settings` 路由和设置模块说明，但本方案文档本身不代替该文档的修改授权。

## 10. 验收标准

| 阶段 | 场景 | 通过条件 |
|---|---|---|
| P0 | 打开设置页 | 桌面侧边栏、移动端导航和直接访问 /settings 均可进入 |
| P0 | 主题切换 | 浅色、深色、跟随系统立即生效，刷新后状态保持 |
| P0 | 配置读取 | GET /api/settings 返回有效配置快照、来源和 secret status，不返回完整密钥 |
| P0 | 配置加载失败 | 显示原因、重试入口和已成功加载的内容；不能把失败显示成默认配置已生效 |
| P0 | 数据目录与运行状态 | Electron 可打开数据目录并读取 sidecar 状态；浏览器显示明确能力限制 |
| P0 | 键盘与响应式 | 可完成分区切换和错误恢复；375px、768px、1440px 下无页面级横向滚动 |
| P0 | 深色模式 | 表单、边框、错误、成功和禁用状态保持可读 |
| P1 | 保存非敏感配置 | 字段校验、版本冲突、原子写入和失败回滚正确；新 ReviewTask 使用新配置 |
| P1 | 配置生效边界 | 当前审查不被中途修改；新 Prompt 会话和新任务使用新的有效配置 |
| P1 | 测试模型服务 | 使用当前有效凭据，成功、认证失败、超时和服务不可用均有可理解反馈 |
| P1.5 | 凭据管理 | safeStorage 保存、清除和状态查询正确，失败时旧凭据仍保留 |
| P1.5 | sidecar 重启 | 显示重启中、成功、失败和恢复入口，重启后 /api/ready 恢复 |
| P1.5 | 凭据安全 | 凭据不出现在日志、命令行、URL、审查日志、普通诊断信息或完整接口响应中 |

## 11. 验证方案

### 11.1 后端

至少增加以下测试：

- 设置响应不包含完整 API Key、GitHub Token 或 Gitee Token；
- 默认值、环境变量、用户配置文件的优先级和字段来源正确；
- `schema_version` 不支持、配置文件损坏、原子替换失败和权限不足时保留上一份有效配置；
- 并发保存的 `expected_version` 冲突被拒绝，不覆盖较新的配置；
- 非法范围、非法枚举、空模型名、未接入消费者的字段和不可写目录被拒绝；
- 配置保存返回正确的 config_version、逐字段 changed、requires_restart 和 effective_for；
- ReviewTask 领取时生成配置快照，当前任务不会被后续保存改变；
- Prompt 新会话使用新的 TTL/容量/上下文限制，已有会话维持原有契约；
- LLM 连接测试能够区分成功、认证失败、超时和服务不可用；
- Git 主机连接测试不会把凭据写入日志；
- CRG 开关和 Reviewer 超时各自有真实消费者和回归测试，未接入前不得出现在响应模型；
- 配置加载失败时保留原配置，不产生半保存状态；
- `/api/settings` router 已在 `backend/app/main.py` 注册；
- 历史审查、仓库管理和提示词接口不受设置 API 影响。

### 11.2 前端

至少覆盖：

- 设置导航与 /settings 路由加载；
- 主题切换和刷新恢复；
- 表单草稿、脏状态、保存中、成功和失败状态；
- 字段级错误位置和 aria-live 错误播报；
- Electron 与浏览器能力差异；
- 设置 API 失败时的重试；
- 375px、768px、1440px 和深色模式布局。

### 11.3 桌面端

设置涉及 preload、sidecar 或凭据存储时，额外验证：

- preload 只暴露预期方法；
- safeStorage 不可用时保存操作被拒绝且不覆盖旧凭据；
- 凭据从 safeStorage 到 sidecar 的传递不经过命令行、URL 或普通日志；
- sidecar 重启后 /api/ready 恢复；
- 应用关闭时没有残留后端进程；
- 数据目录始终使用用户数据目录；仓库目录按用户选择的绝对路径策略校验，不自动搬迁既有仓库；
- API Key 和 Token 不出现在 sidecar 标准输出、错误输出和应用普通日志。

## 12. 推荐实施顺序

1. 记录工作区基线，保存 `git status --short`、目标文档差异和既有 UI 改动清单；确认 `docs/system-design.md` 与当前 React 19、Tailwind 和提示词路由的差异。
2. 冻结配置字段清单，逐项记录真实消费者、生效时机、配置来源、默认值、范围和测试用例；删除或延后没有消费者的字段。
3. 固定 RuntimeSettings、settings.json、配置优先级、schema_version、原子写入和 config_version 契约。
4. 先实现 GET /api/settings、脱敏响应模型和 `backend/app/main.py` 路由注册，再实现 P0 页面、路由、导航、主题设置和运行状态概览。
5. 完成浏览器与 Electron 模式差异提示、P0 前端测试、后端接口测试和桌面桥接测试。
6. 经 P0 验证后进入 P1：实现 SettingsStore、非敏感 PATCH、任务级配置快照和连接测试；先验证实际审查与提示词行为确实使用新值。
7. 最后单独设计和实施 P1.5：safeStorage、凭据传递、清除和 sidecar 重启，不与设置页视觉改造混成一个大批次。
8. 实现完成后同步更新 `docs/system-design.md` 的 `/settings` 路由、配置模块和运行时数据流说明，并单独验证文档与代码一致。

## 13. 完成定义

P0 完成需要同时满足：

1. 设置页能够从桌面和移动端导航进入，直接访问 /settings 可正常加载；
2. 主题设置可用并保持刷新后的状态；
3. GET /api/settings 已注册并返回版本化、脱敏的有效配置快照、配置来源和 secret status；
4. 当前运行模式、版本、API 地址、数据目录、模型配置状态和 Git 配置状态可查看；
5. 敏感值已经脱敏，页面、接口和普通日志中没有完整密钥；
6. 加载失败、后端不可用和桌面能力不可用时都有清晰恢复路径；
7. P0 没有写入非敏感配置、敏感凭据或启动参数，也没有宣称这些能力已经生效；
8. 前端 build、lint 和 P0 新增测试通过；
9. 后端单元测试、语法检查和设置 API 读取测试通过；
10. Electron 现有桥接白名单、`openPath`、`onBackendState` 和 sidecar 状态行为完成验证；
11. 本轮实现未混入工作区原有未提交改动。

P1 和 P1.5 不能以“页面显示新值”作为完成条件，必须分别满足第 10 节对应阶段的存储、运行时、凭据和重启验收。
