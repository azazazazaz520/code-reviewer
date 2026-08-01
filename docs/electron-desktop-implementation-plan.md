# Electron 桌面应用实施方案

## 1. 目标与范围

将当前 Code Reviewer 从“浏览器访问的本地 Web 应用”扩展为“可安装、可独立运行的 Windows 桌面应用”。桌面版使用 Electron 作为宿主，继续复用现有 React/Vite 前端、FastAPI 后端和 Python 审查引擎。

本方案解决以下问题：

- 用户双击应用即可启动，不需要手动运行 Python、uvicorn 或 Vite。
- Electron 主进程负责窗口、系统能力和 Python 后端进程生命周期。
- React 渲染进程只负责界面，不直接访问 Node.js 或文件系统。
- FastAPI 后端继续承担仓库管理、审查任务、报告生成和 SQLite 持久化。
- 保留浏览器开发模式和 FastAPI 单进程生产模式，桌面版是新增运行形态。
- 为后续类似 Codex 的工作台界面保留清晰的宿主层与渲染层接口。

不在本阶段处理：

- 不迁移审查引擎到 Node.js。
- 不改写现有 REST API 为 Electron 专用协议。
- 不引入账号系统、云端同步或远程执行服务。
- 不把所有现有页面一次性重做为新的 UI。

## 2. 已确定的技术决策

| 领域 | 决策 | 原因 |
|---|---|---|
| 桌面宿主 | Electron | 与现有 React/TypeScript 前端衔接直接，Windows 打包和调试成熟 |
| 渲染层 | 保留 `frontend/` 的 React + Vite | 避免重复建设 UI 和路由 |
| 本地服务 | FastAPI 作为 sidecar 进程 | 保留 Python 审查引擎及现有依赖 |
| 进程通信 | Renderer → Preload → Main；业务数据继续走 HTTP | 限制 Node 权限，减少 Electron 专用接口 |
| 数据库 | SQLite | 当前应用已经使用 SQLite，适合本地单用户场景 |
| 后端打包 | 第一阶段使用 PyInstaller one-folder | 启动和资源问题更容易诊断，后续再评估 one-file |
| 桌面打包 | `electron-builder` + Windows NSIS | 支持安装包、快捷方式和后续自动更新扩展 |
| 开发入口 | 新增 `desktop/`，保留 `start.py` | 桌面开发和 Web 开发互不干扰 |

## 3. 目标架构

```text
┌──────────────────────────────────────────────────────────┐
│ Electron 主进程                                           │
│                                                          │
│  BrowserWindow                                            │
│  SidecarManager ── 启动/探活/退出 FastAPI                │
│  DesktopBridge ─── 文件夹选择、打开路径、系统菜单         │
│  AppConfig ─────── 数据目录、端口、日志、运行模式           │
└──────────────────────┬───────────────────────────────────┘
                       │ preload 暴露的最小接口
┌──────────────────────▼───────────────────────────────────┐
│ React Renderer                                            │
│                                                          │
│  Dashboard / Repo / Review 工作台                         │
│  API Client ─────────────── HTTP ───────────────┐         │
└─────────────────────────────────────────────────┼─────────┘
                                                  │
                         127.0.0.1:动态端口       │
┌─────────────────────────────────────────────────▼─────────┐
│ FastAPI sidecar                                           │
│                                                          │
│  REST API → ReviewTaskRunner → Workflow → LLM/CRG         │
│              │                                             │
│              ├── SQLite                                  │
│              ├── Git repositories                         │
│              └── Review logs/reports                       │
└──────────────────────────────────────────────────────────┘
```

### 3.1 进程职责

Electron 主进程只负责桌面生命周期和系统集成，不承载审查业务规则。FastAPI 仍然是业务模块的唯一入口，浏览器版和桌面版使用同一套业务接口。

Renderer 不获得 Node.js 能力。`contextIsolation`、`sandbox` 和 `nodeIntegration: false` 作为默认安全配置；所有需要系统能力的操作必须通过受限的 preload 接口完成。

## 4. 目录结构调整

建议新增独立的 `desktop/` 工作区：

```text
E:/code-reviewer/
├── backend/
│   ├── app/
│   ├── prompts/
│   └── desktop_entry.py          # sidecar 启动入口
├── frontend/
│   ├── src/
│   └── dist/                     # 桌面生产包使用的静态资源
├── desktop/
│   ├── src/
│   │   ├── main.ts               # Electron 主进程入口
│   │   ├── preload.ts             # 最小安全桥接
│   │   ├── sidecar-manager.ts    # 后端进程管理
│   │   ├── app-config.ts         # 运行目录和环境配置
│   │   └── desktop-bridge.ts     # 对话框、路径和系统能力
│   ├── resources/
│   │   └── backend/              # PyInstaller 产物
│   ├── package.json
│   ├── tsconfig.json
│   └── electron-builder.yml
├── docs/
│   └── electron-desktop-implementation-plan.md
└── start.py                      # 继续作为 Web 开发入口
```

`desktop/` 是桌面宿主的独立模块，只有 `frontend/` 和已打包的 backend 产物是它的外部依赖。这样 Electron 的依赖、构建脚本和发布配置不会污染前端业务代码。

## 5. 关键接口设计

### 5.1 SidecarManager 接口

SidecarManager 是桌面宿主和 Python 后端之间的深模块。调用方只需要知道启动、等待就绪和停止，不需要了解端口探测、子进程退出码、日志重定向和超时细节。

```ts
type SidecarState =
  | { status: "starting" }
  | { status: "ready"; baseUrl: string; pid: number }
  | { status: "failed"; message: string; exitCode?: number }
  | { status: "stopped" };

interface SidecarManager {
  start(): Promise<{ baseUrl: string }>;
  stop(): Promise<void>;
  getState(): SidecarState;
  onStateChange(listener: (state: SidecarState) => void): () => void;
}
```

实现约束：

- 传入 `--host 127.0.0.1 --port 0`，由操作系统分配端口，避免固定端口冲突。
- 启动后轮询 `/api/health` 或新增 `/api/ready`，确认服务可接受业务请求后才创建窗口。
- 记录 stdout、stderr 和退出码；启动失败必须在 UI 中展示可操作错误。
- 应用退出时先请求 sidecar 优雅退出，再在超时后终止子进程。
- 不能通过字符串拼接命令启动进程；可执行文件路径和参数必须分别传入。
- 开发模式启动 Python 模块，生产模式启动打包后的 sidecar 可执行文件。

### 5.2 Preload 接口

Preload 只暴露桌面运行时能力，不暴露 `ipcRenderer`、`process` 或任意 Node API：

```ts
interface DesktopRuntime {
  getInfo(): Promise<{
    mode: "development" | "production";
    apiBaseUrl: string;
    dataDir: string;
    appVersion: string;
  }>;
  chooseDirectory(): Promise<string | null>;
  openPath(path: string): Promise<{ ok: boolean; error?: string }>;
  onBackendState(listener: (state: SidecarState) => void): () => void;
}

declare global {
  interface Window {
    desktop?: DesktopRuntime;
  }
}
```

Renderer 的默认行为：

- 浏览器开发模式：使用 `/api`，由 Vite proxy 转发到 `127.0.0.1:8000`。
- Electron 开发模式：从 `window.desktop.getInfo()` 获得动态 `apiBaseUrl`。
- Electron 生产模式：使用 sidecar 的动态地址，或由 FastAPI 同源提供前端时使用相对 `/api`。

业务组件不直接判断 Electron 环境；判断和地址选择集中在 `frontend/src/api/client.ts` 与运行时适配器中。

### 5.3 后端启动接口

新增 `backend/app/desktop_entry.py`，负责读取桌面进程传入的配置并启动 Uvicorn：

```text
python -m app.desktop_entry --host 127.0.0.1 --port 0 --data-dir <path>
```

建议支持的参数：

| 参数 | 说明 |
|---|---|
| `--host` | 只允许绑定本机回环地址 |
| `--port` | 支持 `0`，使用动态端口 |
| `--data-dir` | SQLite、仓库和审查产物的根目录 |
| `--frontend-dist` | 生产模式下的前端静态资源目录 |
| `--ready-file` | 可选，写入实际端口和进程信息 |

当前 `backend/app/config.py` 使用相对路径。桌面模式必须把数据库和仓库路径改为显式绝对路径，避免工作目录变化导致数据落到安装目录或临时目录。

## 6. 数据目录与配置

Windows 默认数据目录建议为 Electron 的 `userData` 目录下的 `data/`：

```text
%APPDATA%/Code Reviewer/
├── data/
│   ├── code_reviewer.db
│   ├── repos/
│   └── reviews/
├── logs/
└── config.json
```

规则：

- 安装目录只存程序和只读资源，不存 SQLite、仓库和审查日志。
- 用户可在设置中修改仓库根目录；修改后只影响新创建或重新同步的仓库。
- API Key 不写入仓库目录、命令行参数或普通日志。
- 第一阶段继续兼容 `.env`，桌面设置页面写入配置文件的实现放在后续阶段。
- 后续需要持久化密钥时，优先使用 Electron `safeStorage`，并提供清除配置入口。
- 卸载程序时不默认删除用户数据，避免误删审查历史和克隆仓库。

## 7. 前端与 Codex 风格工作台的演进路径

Electron 迁移本身不要求一次完成 UI 重做。建议按以下顺序演进：

### 第一阶段：保留现有页面

- 现有 Dashboard、RepoList、RepoDetail、ReviewDetail 直接运行在 Electron 窗口中。
- 只增加启动中、后端异常、后端重启和数据目录错误状态。
- 验证桌面壳、API 地址和窗口生命周期正确。

### 第二阶段：工作台布局

- 左侧固定导航：仓库、最近审查、设置。
- 中央主工作区：当前审查、差异、Finding 和执行日志。
- 右侧上下文区：审查策略、校验摘要、审查状态和操作建议。
- 顶部保留全局命令入口、仓库选择和新建审查入口。
- 审查运行过程中使用事件流或轮询更新工作区，不跳转到多个孤立页面。

### 第三阶段：任务与报告统一模型

把“审查任务”作为 UI 的主对象，统一表示：

- 待启动、运行中、已完成、审查不完整、失败。
- 当前执行步骤和最近日志。
- 确定性校验结果与 Reviewer 结果的区别。
- Finding、未知项、审查覆盖范围和报告质量状态。

这一步应复用现有后端字段，先改善信息组织，再考虑新增实时通信协议。

## 8. 分阶段实施计划

### 阶段 0：基线与契约冻结

目标：在新增 Electron 前确认现有 Web 形态不退化。

工作项：

1. 固定当前 `frontend` 的 build 命令和 `backend` 的测试命令。
2. 梳理 API Client 中所有绝对地址和固定端口引用。
3. 确定 `/api/health` 的响应格式，并新增 `/api/ready` 的语义：服务启动完成且数据库初始化成功。
4. 为 `review_status=complete/degraded`、sidecar 启动失败和报告读取失败补充类型与测试。

完成标准：浏览器开发模式、FastAPI 生产模式和现有审查质量测试均保持通过。

### 阶段 1：Electron 开发壳

目标：启动一个 Electron 窗口，并加载现有 React 应用。

工作项：

1. 新建 `desktop/` package，加入 Electron、TypeScript、构建脚本和开发并发启动脚本。
2. 创建主进程和 preload，开启 `contextIsolation`，关闭 `nodeIntegration`。
3. 开发模式启动 Vite，生产模式加载 `frontend/dist/index.html` 或 sidecar 地址。
4. 增加窗口关闭、单实例和二次启动聚焦已有窗口的处理。

完成标准：执行一个桌面开发命令后能看到现有 Dashboard，刷新、路由和打开外部链接行为正常。

### 阶段 2：Sidecar 生命周期

目标：Electron 能可靠管理 FastAPI。

工作项：

1. 实现 `SidecarManager`。
2. 实现 `backend/app/desktop_entry.py`，支持动态端口和绝对数据目录。
3. 增加 `/api/ready`，将“进程已启动”和“服务可用”区分开。
4. 加入启动超时、异常退出、日志文件和优雅停止。
5. 将 sidecar 状态通过 preload 传给 Renderer，显示启动进度和失败原因。

完成标准：重复启动、关闭、异常退出、端口占用和数据库初始化失败都有明确结果，不留下孤儿 Python 进程。

### 阶段 3：Renderer 运行时适配

目标：前端同时支持浏览器和 Electron。

工作项：

1. 把 API Client 的地址解析集中到一个运行时适配器。
2. 删除业务代码中的固定 `127.0.0.1:8000` 假设。
3. 增加桌面目录选择、打开仓库目录和复制诊断信息能力。
4. 增加 sidecar 启动中、不可用、重启中和审查不完整的 UI 状态。
5. 让错误提示包含下一步操作，而不是只显示底层异常。

完成标准：同一份 React 业务代码可在 Vite 浏览器模式和 Electron 桌面模式运行。

### 阶段 4：Python sidecar 打包

目标：用户设备不需要预装 Python 环境。

工作项：

1. 用 PyInstaller one-folder 打包后端入口。
2. 收集 `backend/prompts/`、CRG 相关资源和必要的运行时文件。
3. 配置工作目录、环境变量和日志目录。
4. 在干净 Windows 环境安装包并执行健康检查。
5. 确认 sidecar 退出时 SQLite 连接、审查 worker 和子进程都能清理。

完成标准：干净机器只安装桌面安装包即可启动应用、创建仓库并完成一次本地提交审查。

### 阶段 5：安装包与发布

目标：生成可分发的 Windows 安装包。

工作项：

1. 配置 `electron-builder` 的 appId、产品名、图标、NSIS 安装器和输出目录。
2. 将前端 dist、Electron 主进程和 Python sidecar 作为明确的资源输入。
3. 增加版本号与构建信息页，便于用户反馈问题。
4. 增加安装、升级、卸载和数据保留测试。
5. 后续再评估代码签名和自动更新，不在首个可用版本阻塞发布。

完成标准：安装包可安装、启动、卸载；升级不会覆盖用户数据；日志能定位启动和审查失败。

### 阶段 6：工作台 UI 演进

目标：在桌面壳稳定后，逐步形成面向审查任务的工作台。

工作项：

1. 先改造全局布局和导航，不改审查引擎。
2. 把 ReviewDetail 拆为任务头部、执行时间线、Finding 列表、校验摘要和上下文面板。
3. 增加快捷键、命令入口和最近任务恢复。
4. 对长日志、差异和大文件采用虚拟滚动或分段加载。
5. 为 degraded、无 Finding、Reviewer 输出异常等情况设计清晰的状态层级。

完成标准：用户能从“选择仓库”到“查看报告”在一个连续工作区内完成主要流程，并且能区分“没有发现问题”和“审查没有完整执行”。

## 9. 测试与验收

### 9.1 单元测试

- `SidecarManager`：动态端口、探活成功、启动超时、异常退出、重复 stop。
- 配置解析：开发/生产模式、绝对数据目录、空配置和非法路径。
- Renderer 运行时适配器：浏览器 `/api`、桌面动态地址、sidecar 不可用。
- Preload 白名单：只暴露预期方法，不能获得任意 IPC 通道。

### 9.2 集成测试

- Electron 启动后 `/api/ready` 成功。
- 提交 local commit 审查并读取报告。
- 关闭 Electron 后没有残留 Python/uvicorn 进程。
- sidecar 失败时窗口展示错误且日志可导出。
- 应用重启后能读取上一次的仓库和审查历史。

### 9.3 发布前手工验收

| 场景 | 预期结果 |
|---|---|
| 无 Python 环境 | 应用正常启动 |
| 端口 8000 被占用 | 桌面版仍能使用动态端口 |
| LLM 配置为空 | 应用可启动，审查失败原因清楚 |
| 审查 Reviewer 输出无法解析 | 报告标记为审查不完整，不显示为绿色通过 |
| 安装目录无写权限 | 数据写入用户数据目录 |
| 应用强制关闭后重启 | SQLite 可恢复，任务状态可解释 |
| 卸载后重新安装 | 用户数据按产品策略保留或明确提示 |

建议的验证命令：

```powershell
# 后端
backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_*.py" -q

# 前端
Set-Location frontend
npm.cmd run build

# 桌面包
Set-Location ..\desktop
npm.cmd run build
npm.cmd run package:win
```

## 10. 风险与应对

| 风险 | 应对 |
|---|---|
| Electron 体积较大 | 首个版本优先保证稳定和调试能力；后续再评估更轻量宿主 |
| Python sidecar 包体积大 | 使用 one-folder，清理不需要的依赖和资源；将体积作为发布指标 |
| 子进程残留 | 统一由 SidecarManager 管理，记录 pid，退出时等待并兜底终止 |
| 工作目录导致数据丢失 | 所有桌面路径由 Electron 解析为绝对路径并显式传给后端 |
| Renderer 权限过大 | 禁止 Node 注入，preload 只暴露白名单接口 |
| 开发模式和生产模式地址不一致 | API Client 只依赖运行时配置，不在页面中写死端口 |
| 审查任务运行时间长 | 保留后端 worker 和轮询机制，后续再引入 SSE，不把实时通信作为首个桌面版本前置条件 |
| 自动更新覆盖数据 | 更新包只替换程序资源，数据目录独立；升级测试必须包含历史报告 |

## 11. 首个可用版本的范围

首个桌面版本建议只包含以下闭环：

1. 安装并启动 Electron 应用。
2. 自动启动 FastAPI sidecar。
3. 查看和管理已有仓库。
4. 发起 local commit 审查。
5. 查看进度、日志、报告和审查完整性状态。
6. 重启应用后保留本地数据。
7. 生成 Windows 安装包。

以下内容延后：

- GitHub OAuth 和 PR WebView。
- 实时 SSE/WebSocket 通信。
- 多窗口、多用户和云端同步。
- 自动更新服务。
- 代码签名自动化。
- 完整的工作台视觉重构。

## 12. 建议的第一批实现任务

按以下顺序开工：

1. 新增 `desktop/` package 和 Electron 最小窗口。
2. 新增 `SidecarManager`，先在开发模式启动当前 FastAPI。
3. 新增 `/api/ready` 与 `desktop_entry.py`。
4. 修改 API Client，使浏览器和 Electron 使用不同运行时地址但共享业务代码。
5. 加入 Electron 启动/停止/异常退出测试。
6. 在稳定的开发模式基础上增加 PyInstaller 和 electron-builder。
7. 最后再推进工作台 UI 改造。

这个顺序的核心判断是：先验证“Electron 能稳定承载现有应用”，再处理打包和 UI 演进。每个阶段都保留可运行结果，出现问题时可以明确定位在宿主、sidecar、运行时适配还是业务代码。
