# 远程仓库与本地工作区审查实施方案

## 1. 背景

当前 Code Reviewer 为每个仓库创建一个本地 clone，并从该 clone 中解析分支或 Commit，使用临时 detached worktree 执行审查。这个模型适合审查已经推送到远程仓库的代码，但不能覆盖用户真实开发目录中的未推送 Commit、已暂存修改、未暂存修改和未跟踪文件。

普通 clone 还会创建本地默认分支。执行 fetch 后，`origin/<branch>` 可能已经指向远程新提交，而本地 `<branch>` 仍停留在旧提交。若优先解析本地分支，审查结果就可能不是远程最新版本。

本方案将代码来源明确拆成两类：

1. **远程仓库来源**：使用审查软件维护的本地 clone，fetch 后以 `origin/<branch>` 为远程版本来源。
2. **本地工作区来源**：直接读取用户选择的本地 Git 工作区，创建只读临时快照，不修改用户文件。

## 2. 目标与非目标

### 2.1 目标

- 识别远程分支自上次同步以来是否有新提交。
- “审查最新提交”在提交任务时同步远程分支，并锁定具体 `head_revision`。
- 支持审查本地工作区的未推送 Commit、暂存修改、未暂存修改和未跟踪文件。
- 审查过程不 checkout、merge、pull、stash、reset 或修改用户工作区。
- 每条 ReviewTask 都能说明代码来源、目标版本、对比基准和快照状态。
- 保持现有 PR 审查、审查报告、Diff 和历史记录的兼容性。

### 2.2 非目标

- P0 不实现远程仓库自动后台轮询。
- P0 不实现 GitHub/Gitee Webhook 服务端接入。
- P0 不把用户工作区内容上传到远程服务。
- P0 不支持修改用户工作区中的 submodule、Git LFS 对象或外部生成资源。

## 3. 已确定的核心决策

### 3.1 远程 clone 是审查缓存，不是用户工作区

`Repo.local_path` 表示由应用管理的审查缓存目录。用户不在此目录开发，也不应依赖其中的本地 `main`、`master` 等分支。

远程审查的权威来源是本地 Git 数据库中的远程跟踪引用：

```text
远程仓库 → git fetch origin --prune → 本地 origin/main → 解析 SHA → 临时 detached worktree → 审查
```

`git fetch` 只更新本地 Git 对象和 `refs/remotes/origin/*`，不 checkout、merge 或修改工作区。

### 3.2 审查任务必须锁定版本

提交审查时不能只保存 branch 名称。任务必须保存当时解析出的 `head_revision`，Worker 后续只能使用这个 SHA。

```text
任务提交时：origin/main = B，任务锁定 B
任务执行前：origin/main = C
最终报告：仍然审查 B
```

旧报告不随远程分支移动而改变；用户需要再次审查 C 时创建新任务。

### 3.3 本地工作区是独立来源

用户本地工作区不通过远程 clone 间接获取。工作区审查直接读取用户选择的 Git 仓库目录，并在临时目录中重建审查快照。

## 4. 当前实现与差距

当前相关逻辑：

- 添加仓库时执行一次 `git clone`，结果写入 `Repo.local_path`。
- `GET /api/repos/{id}/branches` 会执行 `git fetch --all --prune`，然后同时读取本地分支和远程分支。
- 分支解析优先尝试本地 `<branch>`，再尝试 `origin/<branch>`。
- Local ReviewTask 只保存 `branch` 或 `commit_hash`，没有保存提交时的 SHA。
- `create_review_snapshot` 从注册仓库的 `local_path` 创建临时 worktree，不读取用户实际开发目录。
- 当前界面中的“Local Commit”表示审查应用 clone 中的 Commit，不表示用户本地工作区。

需要调整：

1. 将同步从分支查询中分离出来。
2. 远程分支只解析 `refs/remotes/origin/<branch>`。
3. 提交任务时完成同步和版本锁定。
4. 增加本地工作区审查来源和安全快照机制。
5. 在 UI 中明确区分“远程仓库”和“本地工作区”。

## 5. 统一代码来源模型

新增内部来源类型 `source_type`：

```text
pr | remote_latest | remote_commit | workspace
```

| source_type | 来源 | 目标版本 | 默认对比基准 |
|---|---|---|---|
| `pr` | GitHub/Gitee PR | PR head SHA | PR base SHA |
| `remote_latest` | 应用维护的远程 clone | fetch 后的 `origin/<branch>` SHA | 指定 base branch 或目标提交的父提交 |
| `remote_commit` | 应用维护的远程 clone | 指定 Commit SHA | 指定 base branch 或目标提交的父提交 |
| `workspace` | 用户选择的本地工作区 | 工作区当前状态或本地 HEAD | 工作区 HEAD 或指定基准 |

保留现有 `review_type` 字段用于历史兼容；新代码以 `source_type` 判断代码来源，避免继续把 PR、远程 Commit 和本地工作区都塞进 `local`。

## 6. 数据模型调整

### 6.1 repositories

现有字段继续保留，并增加远程同步状态：

| 字段 | 类型 | 说明 |
|---|---|---|
| `default_branch` | 字符串，可空 | 最近一次同步得到的远程默认分支 |
| `last_synced_at` | 时间，可空 | 最近一次成功 fetch 时间 |
| `sync_status` | 字符串 | `never`、`syncing`、`ready`、`failed` |
| `sync_error` | 文本，可空 | 最近一次同步错误，不记录 Token |

### 6.2 repository_refs

新增远程分支引用快照表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `repo_id` | 外键 | 所属仓库 |
| `name` | 字符串 | 分支名，如 `main` |
| `remote_ref` | 字符串 | 如 `refs/remotes/origin/main` |
| `head_revision` | 字符串 | 最近一次同步得到的完整 SHA |
| `updated_at` | 时间 | 本地记录更新时间 |

唯一约束为 `(repo_id, name)`。同步时更新已有分支，删除已经不存在的远程分支记录。

### 6.3 review_tasks

增加以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `source_type` | 字符串 | `pr`、`remote_latest`、`remote_commit`、`workspace` |
| `source_path` | 字符串，可空 | 本地工作区绝对路径；远程来源为空 |
| `head_revision` | 字符串，可空 | 任务提交时锁定的目标 SHA |
| `base_revision` | 字符串，可空 | 任务提交时锁定的对比基准 SHA |
| `workspace_fingerprint` | 字符串，可空 | 工作区快照指纹 |
| `workspace_stats_json` | 文本，可空 | 暂存、未暂存、未跟踪文件数量等摘要 |

历史任务允许这些字段为空。历史报告展示时继续使用现有 `commit_hash`、`branch` 和 `changes` 字段。

## 7. API 设计

### 7.1 远程同步

```text
POST /api/repos/{repo_id}/sync
```

执行：

1. 校验仓库和本地 clone 路径。
2. 以仓库级锁防止多个同步同时操作同一个 Git 数据库。
3. 执行 `git fetch origin --prune`。
4. 读取 `refs/remotes/origin/*` 和 `origin/HEAD`。
5. 更新 `repository_refs` 和仓库同步状态。
6. 返回分支头变化摘要。

响应至少包含 `status`、`checked_at`、`default_branch` 和分支的 `head_revision`、`previous_revision`、`has_new_commits`。

### 7.2 分支查询

```text
GET /api/repos/{repo_id}/branches
```

改为只读接口，不执行 fetch，只返回最近一次同步得到的远程分支快照。尚未同步时返回明确状态，由前端决定是否调用同步接口。

### 7.3 远程最新提交审查

```json
{"source_type":"remote_latest","branch":"main","base_branch":"main"}
```

后端在 ReviewTask 进入 Worker 的准备阶段再次执行同步，解析 `origin/main`，写入 `head_revision` 和 `base_revision`，之后 Worker 不再根据 branch 重新解析版本。这样不会让提交审查的 HTTP 请求长时间等待远程网络操作；任务详情会先显示等待/准备状态。

### 7.4 本地工作区审查

```json
{"source_type":"workspace","workspace_path":"D:/projects/example","workspace_target":"working_tree","base_revision":"HEAD"}
```

`workspace_target` 包含：

- `working_tree`：HEAD 加上暂存、未暂存和未跟踪修改；
- `head_commit`：当前本地 HEAD 及其相对基准；
- `commit`：用户指定的本地 Commit SHA。

`working_tree` 的基准固定为当前工作区 HEAD；它审查的是 HEAD 之上的暂存、未暂存和未跟踪内容，不包含 HEAD 之前的历史提交。

桌面版优先通过 Electron 的目录选择接口获取路径；浏览器开发模式只允许后端明确配置的本地路径，不接受任意远程请求传入的路径。

## 8. 远程来源实现

### 8.1 同步规则

- 只使用 `origin` 远程，不将本地分支作为远程最新来源。
- 分支解析固定使用 `refs/remotes/origin/<branch>`。
- `origin/HEAD` 用于识别默认分支。
- 远程分支不存在时返回错误，不回退到同名本地分支。
- 指定 SHA 时先确认对象存在；不存在则 fetch 指定 SHA，失败后返回可理解错误。
- 不执行 `git pull`、merge 或 checkout。

### 8.2 版本锁定

创建任务的事务应同时保存 `branch`、`head_revision` 和 `base_revision`。Worker 接收到任务后只使用这两个 SHA 创建 ReviewSnapshot，报告中的 `changes` 也返回这两个 SHA。

### 8.3 更新提示

P0 提供手动“同步”按钮，并在进入 RepoDetail 或发起审查弹窗时允许按需同步。UI 展示最近同步时间、当前远程分支头 SHA、上次审查的 `head_revision` 和是否存在新提交。

不在 P0 中持续轮询远程仓库。后续可以增加定时同步或 Webhook，但发现更新与执行审查仍然必须通过 SHA 锁定。

## 9. 本地工作区快照实现

### 9.1 工作区校验

后端接收路径后：

1. 规范化绝对路径并确认目录存在。
2. 执行 `git rev-parse --show-toplevel` 确认是 Git 仓库。
3. 记录解析后的仓库根目录，不使用用户传入的相对路径作为快照根。
4. 限制路径访问来源：桌面版在仓库管理中使用目录选择器登记本地仓库；浏览器模式需要本地部署配置允许。
5. 拒绝路径穿越、工作区根目录外的文件复制和 `.git` 目录复制。

### 9.2 状态采集

至少执行 `git rev-parse HEAD`、`git status --porcelain=v1 -z`、`git diff HEAD --binary` 和 `git ls-files --others --exclude-standard -z`。

需要覆盖已提交但未推送的本地 Commit、已暂存修改、未暂存修改、删除文件、重命名文件和未跟踪文件。忽略文件不进入快照；二进制变更必须保留为二进制 Patch 或复制到临时快照。

### 9.3 临时快照

工作区审查不得修改原目录。建议流程：

1. 读取工作区 HEAD，创建基于 HEAD 的临时 detached worktree。
2. 将 `git diff HEAD --binary` 应用到临时 worktree。
3. 将未跟踪文件按相对路径复制到临时 worktree。
4. 重新计算临时快照的 Diff、变更文件和文件内容。
5. 使用现有 Review Workflow 审查临时根目录。
6. 审查结束后清理临时 worktree 和复制文件。

若 Patch 应用失败，任务应失败并说明“工作区在采集期间发生变化”，不能静默退回审查旧版本。

### 9.4 一致性与指纹

采集前后分别获取工作区状态摘要。指纹至少包含 HEAD SHA、status 内容、tracked diff hash、未跟踪文件路径与内容 hash。

如果采集期间指纹变化，默认终止本次任务并提示用户重新提交，避免报告混合两个时间点的代码。

## 10. 前端交互

### 10.1 仓库详情页

- 显示远程同步状态和最近同步时间。
- 提供“同步远程分支”按钮。
- 分支列表标记为“远程分支”，不再把本地分支和远程分支混为一个名称。
- 远程分支有新提交时显示非阻断提示和“审查最新提交”入口。

### 10.2 发起审查

远程仓库审查来源选择：

```text
远程仓库最新提交
远程仓库指定 Commit
本地工作区
```

本地仓库先在仓库管理中登记。发起审查时选择已登记的本地仓库，再选择“未提交改动”或“指定 Commit”。未提交改动审查使用登记的工作区路径；指定 Commit 审查使用本地 Commit 及其父提交。不显示或修改远程 clone 的本地分支。

### 10.3 报告详情

在 Diff 区域显示来源、目标、基准 SHA 和目标版本 SHA。工作区审查额外显示暂存、未暂存、未跟踪文件数量，以及快照是否在采集期间保持一致。

## 11. 实施顺序

### P0-A：远程来源正确性

1. 增加远程引用快照和同步状态模型。
2. 抽取 `RepoSyncService`，实现 fetch、默认分支识别和分支头读取。
3. 将分支查询改为只读，禁止查询接口隐式 fetch。
4. 远程分支解析固定使用 `origin/<branch>`。
5. ReviewTask 保存 `source_type`、`head_revision`、`base_revision`。
6. 提交远程最新审查前自动同步并锁定 SHA。
7. 增加远程同步、分支移动和任务锁定测试。

### P0-B：本地工作区审查

1. 增加工作区路径校验和 Git 状态采集模块。
2. 实现 tracked diff、staged/unstaged diff 和 untracked 文件收集。
3. 实现只读临时快照和一致性指纹。
4. 将 WorkspaceSnapshot 接入现有 ReviewSnapshot/Workflow 接口。
5. 增加桌面目录选择接口的前端接入。
6. 增加工作区审查入口、状态摘要和来源展示。
7. 增加未提交、未推送、未跟踪、删除和采集中途变化的回归测试。

### P1：体验与效率

1. 仓库详情页显示远程新提交提示。
2. 远程同步结果显示分支变化和新 Commit 数量。
3. 支持用户选择对比基准分支。
4. 支持取消快照采集和清理失败重试。

### P2：主动发现

1. 增加可配置的后台定时同步。
2. 评估 GitHub/Gitee Webhook。
3. 增加“发现更新但不自动审查”的通知策略。

## 12. 测试与验收

### 12.1 远程仓库

1. 初始 clone 后能读取远程默认分支。
2. 远程分支从 A 推送到 B，fetch 后只能解析 B。
3. 本地默认分支停留在 A 时，远程最新审查仍使用 B。
4. 创建任务后远程继续推送 C，任务仍审查已锁定的 B。
5. 远程分支被删除时，不回退到本地同名分支。
6. 指定 Commit SHA 时，报告记录准确的目标和基准 SHA。
7. fetch 超时、Token 无效、远程不存在时，返回可理解错误且不污染同步状态。

### 12.2 本地工作区

1. 只有未提交修改时能生成完整 Diff。
2. 同时存在 staged 和 unstaged 修改时两者都被审查。
3. 未跟踪文件被纳入快照，忽略文件不被纳入。
4. 删除、重命名和二进制文件的变更不丢失。
5. 本地存在未推送 Commit 时能审查当前 HEAD。
6. 审查过程中原工作区文件、分支和 index 不发生变化。
7. 采集前后工作区变化时任务失败，不生成混合报告。
8. 非 Git 目录、无权限目录、路径穿越和复制 `.git` 目录被拒绝。
9. 临时 worktree 在成功、失败和取消后都能清理。

### 12.3 兼容性

1. 旧 ReviewTask 可以继续查看历史报告。
2. 旧 `review_type=local` 任务按历史逻辑读取，新增任务使用 `source_type`。
3. PR 审查仍按 PR head/base SHA 创建快照。
4. Dashboard、仓库统计、归档、Diff 和审查详情不因新增字段失败。
5. 后端单元测试、前端构建和桌面端测试全部通过。

## 13. 失败处理与安全边界

- 同步失败不得更新 `last_synced_at` 或覆盖上一次有效分支头。
- 工作区快照失败不得修改用户 Git 状态，也不得把旧快照当作成功结果。
- API Key、Token、完整本地路径和 Git 错误中的敏感凭据不得写入普通审查日志或 Review Report。
- 单个仓库同步使用锁，避免并发 fetch、worktree 创建和清理互相干扰。
- 临时目录必须使用系统临时目录和显式清理；清理失败需要记录路径并提示用户，不得递归删除未经确认的目录。
- 所有 ReviewTask 报告必须保留来源和版本信息，避免用户误以为报告针对远程当前状态。

## 14. 实现前默认值

以下事项不阻塞 P0，按下列默认值实现并在代码中保留清晰错误提示：

1. 本地工作区默认基准为 `HEAD`；用户选择本地 Commit 时默认基准为父提交。
2. 工作区包含 submodule 时，P0 只报告为未支持状态，不递归读取子仓库。
3. 大型二进制未跟踪文件超过限制时拒绝快照，并给出路径和大小提示。
4. 浏览器开发模式的本地路径访问需要显式配置；Electron 模式优先使用目录选择器。
5. P0 不自动创建审查任务，只在检测到远程更新时提示用户。
