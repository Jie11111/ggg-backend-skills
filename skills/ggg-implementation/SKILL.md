---
name: ggg-implementation
description: 编码实现和已实现代码续改阶段。GGG 基于 full 已确认任务或 quick 已确认边界修改 Java、前端、SQL、配置和脚本，默认不新增测试类；适用于开始编码、继续开发，以及用户主动提出的单点行为修正、tiny 局部修正、补注释/Javadoc、调整异常日志或 Trace。用户主动修改一个明确问题时默认只改必要代码和直接相关联调文档并编译验证，不重走完整 GGG 需求链路；Java 后端自动应用 ggg-java-coding-standard。
---

# GGG Implementation（编码实现）

## 定位

按已确认任务或 quick 边界完成最小、正确、可验证的代码闭环。本阶段负责 Git 基线、实现范围、风险预检、生产代码、开发者验证和差异指纹；默认不新增测试类，不重新解释业务，也不复制语言规范。

- Quick：读取 `ggg/features/YYYYMMDD-需求名/quick.md`。
- Full：读取同目录 `02-design.md`、`03-tasks.md`，按需读取新版 `sql-draft.sql`、历史 `04-schema.sql` 和 `interface-details/`，写入 `05-implementation-log.md`。
- Java、Spring、Dubbo、MyBatis、后端 SQL/DDL 或 Java 测试改动，必须完整读取 `../ggg-java-coding-standard/SKILL.md`；其他语言读取项目自己的构建、格式和测试约定。
- 业务身份、权限、状态、公共契约、SQL/事务、异步顺序或跨项目边界仍未确认时停止实现并路由上游；Quick 影响面失控时升级 Full。

## 用户主动单点续改快速通道

用户在已有实现基础上主动提出一个明确修正时，本节优先于后续标准 Full/Quick 流程。典型表达包括“把这个判断改成……”“这个角色不能……”“这个字段改为……”“这里补一个错误码”。满足以下条件时直接执行：

- 目标行为明确，不需要补充业务选择；
- 影响可收敛到 1～3 个生产代码文件或局部符号；
- 不涉及新增接口、数据库结构、跨项目协议、事务边界、数据迁移或多模块业务重构；
- 可以包含既有接口中的一处权限判断、参数校验、角色规则、错误码、日志或返回字段修正。

快速通道固定执行：

1. 只读确认目标代码、直接调用链和 `git status --short`。
2. 只修改必要生产代码；接口行为或错误契约变化时，仅同步已经存在且直接相关的联调/API 文档。
3. 不自动修改 `00-baseline.md`、`01-research.md`、`02-design.md`、`03-tasks.md`、`05-implementation-log.md`、`meta.json`、Review 或测试报告，不调用 `sync-clarification`、阶段 reset/advance、全量 `validate`，也不重新锁定整套需求基线。
4. 不启动 `implementation-start/precheck/complete` 会话；直接执行目标模块编译，并按需增加最小静态检查和 `git diff --check`。
5. 不新增测试类；只有用户明确要求时才运行或修改专项测试。
6. 最终只报告实际代码/联调文档、编译结果和尚未执行的环境验证。

只有用户明确要求“同步全套 GGG 文档”“重新走需求链路/基线”，或者实际排查发现超出上述边界时，才退出快速通道。因实际影响面扩大需要升级时，先用一句话告知用户原因，不得静默扩展流程。

## 标准 Full/Quick 流程硬约束

- 除“用户主动单点续改快速通道”外，`implementation-start` 和 `implementation-precheck` 必须早于本轮第一处新增代码修改。
- 真实 diff、验证结果和指纹由命令生成；不得手改 `implementation-state.json` 或倒填验证。
- 用户无关脏文件只保护，不覆盖、回滚、格式化或顺手整理；本需求已有差异必须显式接管。
- 默认不创建或修改测试类、测试桩、Fixture 和测试数据工厂；只有用户明确要求测试代码时才实施。验证不足必须如实记录，但不得借此自动扩张测试代码范围。
- 每轮只登记本 Ixx 新增或改变的文件；完成快照仍锁定本需求累计 diff。
- 所有命令默认一次性、非交互、非 PTY 执行；禁止为测试、脱敏或日志采集启动常驻终端、常驻 shell、后台 tail 或等待输入的进程。

## 1. 锁定范围和风险

先只读查看任务、入口、相邻链路、项目工具和 `git status --short`，列出全部涉及仓库。Full 选择本轮 Txx；未显式指定时，首轮采用全部计划任务，后续采用尚未完成的任务；全部任务已完成后的返工必须显式指定归属 Txx。Quick 以确认边界为范围，不使用 `--task`。

按行为风险选档，边界不清时上调一级：

| 档位 | 典型改动 | 必填预检面 |
|---|---|---|
| `tiny` | 注释、格式、确定的局部映射且无契约变化 | 范围与主链路；验证策略 |
| `normal` | 单仓常规业务、局部接口或数据访问变化 | 范围与主链路；代码落点与职责；数据、契约与失败边界；验证策略 |
| `high` | 权限、共享状态、公共接口、Schema、事务、并发、MQ/异步、跨仓或迁移 | normal 四面；性能、外部调用与恢复；抽象选择与方案偏差 |

启动会话：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start \
  --record <05-implementation-log.md或quick.md> \
  --risk-profile <tiny|normal|high> \
  [--task T1 --task T2] \
  --repo-root <Git仓库1> [--repo-root <Git仓库2> ...] \
  [--adopt-existing-file <本需求已有实现文件> ...]
```

多仓库接管文件使用绝对路径。已有进行中 Ixx 时继续该轮；已完成后续改时开启新 Ixx。

如果本需求代码已经提交，不重建隔离 worktree，也不把 `base_head` 偷换成当前
HEAD。直接绑定可审计的提交范围：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start \
  --record <05-implementation-log.md或quick.md> \
  --risk-profile <tiny|normal|high> \
  --repo-root <Git仓库> \
  --diff-range <BASE>..<TARGET>
```

单个普通提交也可使用 `--adopt-commit <COMMIT>`，等价接管其父提交到该提交的
差异。多仓时按 `--repo-root` 顺序分别重复参数；`--diff-range` 与
`--adopt-commit` 不能同时使用。提交范围必须位于当前 HEAD 历史中，且当前
工作区文件必须仍与目标提交一致；同轮还有明确属于本需求的未提交文件时再逐个
使用 `--adopt-existing-file`。

### Tiny amendment 标准记录通道

不符合“用户主动单点续改快速通道”，但仍需纳入正式 GGG 实现记录的低风险局部修正，按 `tiny amendment` 处理，例如删除一个已废弃枚举值、补字段注释、修正序列化类型、补一处日志或 Trace。必须同时满足：

- 影响范围可准确列为 1～3 个局部文件或符号；
- 不新增接口、表结构、权限模型、事务、跨项目契约或新业务分支；
- 用户口径明确，没有需要重新澄清的变量。

用户明确要求保留正式实现记录时，用户的修正消息本身就是 tiny 的执行依据，不再转产品角色、不重复询问 quick/full 或完整需求确认。若已有进行中 Ixx，直接在当前轮次完成；若实现已完成，则开启一个 `tiny` 轮次，只做“范围与主链路、验证策略”两面预检。只更新确实受影响的权威文档行，不重做无关 research、design、tasks，不重建历史提交或隔离 worktree。完成后执行目标编译/静态检查和 diff 复核。Review 仅在用户明确要求时执行，不是实现完成或测试的前置步骤。

## 2. 完成编码前预检

从 Txx/Dxx 指向的类、方法、表、接口和配置进入，查清入口、业务层、Facade/Client、数据访问、DTO/枚举、配置、调用方与现有测试。存在 `.codegraph/` 时优先使用；未命中再直接读代码并用 `rg` 查证。

只填写当前风险档位要求的行，每行一两句并引用 Txx/Dxx、文件、符号、契约或项目约定。范围行必须准确覆盖本轮 Txx；验证策略必须说明最接近行为边界的命令或明确豁免条件。不要扩写成第二份技术方案，也不要补成排“不适用”。

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-precheck \
  --record <05-implementation-log.md或quick.md>
```

预检通过后不得改写；上游或关键实现决策变化时重开 Ixx。

## 3. 按 Txx 形成纵向闭环

按依赖逐个完成：

```text
定位真实链路 → 实现完整行为 → 执行当前快照验证 → 复核 diff → 记录证据
```

- 不跨任务机械地先写完所有 Mapper、Service 或 Controller。
- 只做任务所需的最小设计；不夹带重构、格式化或未来抽象。
- 默认不新增测试类。优先使用编译、静态检查、已有测试、接口请求或业务回查验证；用户明确要求新增/修改测试代码时，才实现最接近行为边界的测试。
- `tiny` 且无行为变化可只运行 formatter、编译或静态检查。
- 无法完整验证时，记录不可行事实、替代验证、剩余风险和后续动作，不把未执行写成通过。
- 设计偏差、完成证据、实际文件、关键 Java 注释和 SQL/DDL 依据只记录一次，不重复抄规范。
- 新增或修改 Request/Response/DTO 字段时逐字段补业务注释；跨 JavaScript 边界的 Long/大整数 ID 按已确认契约使用字符串，避免前端精度丢失，内部 Entity/Mapper 保持数据库真实类型。
- 新增或修改主业务链路时，沿用项目既有业务异常和错误码；在能提供上下文且不重复的位置补异常日志，并接入项目已有 Trace 设施。项目确无对应设施时记录事实，不生造同名框架。

## 4. 用真实命令绑定验证

每条验证通过 CLI 一次性执行，不手写“已通过”：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-verify \
  --record <05-implementation-log.md或quick.md> \
  [--cwd <已声明仓库内目录>] \
  [--label <unit|compile|lint|integration等稳定标签>] \
  [--timeout-seconds 60] \
  -- <命令及参数>
```

命令不经过 shell，以一次性非 PTY 进程运行；默认 60 秒，超时或命令遗留子进程时回收完整进程组，并记录 TERM/KILL 与残留检查。记录命令、cwd、时间、退出码、输出摘要和执行前后代码快照。验证命令若改变实现文件，本次证据标记 stale，确认生成结果后必须重跑。失败先修复，再用同一 `--label` 重跑；当前快照仍有未恢复失败时不能完成。

默认使用非 PTY、有限时长的直接子进程。脱敏在输出采集后由证据工具完成，不为“脱敏”另开常驻终端。只有命令本身明确需要交互且用户已知情时才允许临时交互；结束后立即退出，不保留会话。

局部验证后按影响面扩大到模块或跨仓验证。退出码 0、编译成功或 `git diff --check` 只能证明各自覆盖的事实，不能替代业务断言。

## 5. 漂移与重开

| 漂移 | 处理 |
|---|---|
| 同一决策下的普通落点调整 | 写入偏差记录后继续 |
| 标准 Full/Quick 中的需求、接口、SQL、事务、核心抽象或任务边界变化 | 回写并确认权威上游，再重开 Ixx |
| 预检文字错误且尚未改代码 | 修正后重跑预检 |
| 已改代码但预检失效 | 保留差异，禁止倒填，执行重开 |

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-restart \
  --record <05-implementation-log.md或quick.md> \
  --reason "<旧轮次无法继续的事实原因>"
```

标准 Full/Quick 的上游 baseline 变化时按原工作流同步影响；用户主动单点续改不得仅因局部行为变化自动触发全套上游同步。用户要求撤销时只处理本轮相关改动。

## 6. 完成门禁

重新读取全部声明仓库的 staged、unstaged 和 untracked 差异，核对本轮 Txx、完成标准、当前轮次文件、验证、偏差、默认不新增测试类的执行情况和剩余风险。Full 更新当前 Ixx；Quick 更新对应记录。

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-complete \
  --record <05-implementation-log.md或quick.md>
```

只有环境确实阻断且替代证据、风险已明确时，才显式豁免：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-complete \
  --record <05-implementation-log.md或quick.md> \
  --verification-waiver "<无法执行的事实、替代证据与剩余风险>"
```

豁免保留“未验证”事实，不等同验证通过。Full 完成后再运行工作流 `validate`；用户主动单点续改快速通道不运行全量工作流校验。

最终只报告：完成的 Txx/主链路、关键文件、新鲜验证或豁免、偏差与剩余风险、Ixx 和差异指纹。实现文件、权威输入或后续报告变化时，以状态命令的新鲜度结果为准，不沿用旧结论。
