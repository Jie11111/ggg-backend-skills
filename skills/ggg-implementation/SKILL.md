---
name: ggg-implementation
description: 编码实现和已实现代码续改阶段。GGG 基于 full 已确认任务或 quick 已确认边界修改 Java、前端、SQL、配置、脚本及风险要求的测试；适用于开始编码、继续开发、修正本轮实现、补注释/Javadoc、调整日志或格式。每轮先锁定 Git 基线、Txx 范围和 tiny/normal/high 风险档位，再完成编码前预检、纵向实现与当前快照验证；完成时锁定真实差异指纹，后续代码变化会使完成、Review 和测试结论失效。Java 后端自动应用 ggg-java-coding-standard。
---

# GGG Implementation（编码实现）

## 定位

按已确认任务或 quick 边界完成最小、正确、可验证的代码闭环。本阶段负责 Git 基线、实现范围、风险预检、代码与必要测试、开发者验证和差异指纹；不重新解释业务，也不复制语言规范。

- Quick：读取 `ggg/features/YYYYMMDD-需求名/quick.md`。
- Full：读取同目录 `02-design.md`、`03-tasks.md`，按需读取 `04-schema.sql`、`interface-details/`，写入 `05-implementation-log.md`。
- Java、Spring、Dubbo、MyBatis、后端 SQL/DDL 或 Java 测试改动，必须完整读取 `../ggg-java-coding-standard/SKILL.md`；其他语言读取项目自己的构建、格式和测试约定。
- 业务身份、权限、状态、公共契约、SQL/事务、异步顺序或跨项目边界仍未确认时停止实现并路由上游；Quick 影响面失控时升级 Full。

## 硬约束

- `implementation-start` 和 `implementation-precheck` 必须早于本轮第一处新增代码修改。
- 真实 diff、验证结果和指纹由命令生成；不得手改 `implementation-state.json` 或倒填验证。
- 用户无关脏文件只保护，不覆盖、回滚、格式化或顺手整理；本需求已有差异必须显式接管。
- “用户未要求写测试”不是关键覆盖缺口的豁免理由。
- 每轮只登记本 Ixx 新增或改变的文件；完成快照仍锁定本需求累计 diff。

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
定位真实链路 → 实现完整行为与必要测试 → 执行当前快照验证 → 复核 diff → 记录证据
```

- 不跨任务机械地先写完所有 Mapper、Service 或 Controller。
- 只做任务所需的最小设计；不夹带重构、格式化或未来抽象。
- Bug、核心规则、状态迁移、权限、公共契约、SQL/事务或异步副作用变化，应新增/更新最接近的自动化测试。
- `tiny` 且无行为变化可只运行 formatter、编译或静态检查。
- 无法合理自动化时，记录不可行事实、替代验证、剩余风险和后续动作；时间不足或用户未要求不能单独构成豁免。
- 设计偏差、完成证据、实际文件、关键 Java 注释和 SQL/DDL 依据只记录一次，不重复抄规范。

## 4. 用真实命令绑定验证

每条验证通过 CLI 执行，不手写“已通过”：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-verify \
  --record <05-implementation-log.md或quick.md> \
  [--cwd <已声明仓库内目录>] \
  [--label <unit|compile|lint|integration等稳定标签>] \
  -- <命令及参数>
```

命令不经过 shell；记录命令、cwd、时间、退出码、输出摘要和执行前后代码快照。验证命令若改变实现文件，本次证据标记 stale，确认生成结果后必须重跑。失败先修复，再用同一 `--label` 重跑；当前快照仍有未恢复失败时不能完成。

局部验证后按影响面扩大到模块或跨仓验证。退出码 0、编译成功或 `git diff --check` 只能证明各自覆盖的事实，不能替代业务断言。

## 5. 漂移与重开

| 漂移 | 处理 |
|---|---|
| 同一决策下的普通落点调整 | 写入偏差记录后继续 |
| 需求、接口、SQL、事务、核心抽象或任务边界变化 | 回写并确认权威上游，再重开 Ixx |
| 预检文字错误且尚未改代码 | 修正后重跑预检 |
| 已改代码但预检失效 | 保留差异，禁止倒填，执行重开 |

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-restart \
  --record <05-implementation-log.md或quick.md> \
  --reason "<旧轮次无法继续的事实原因>"
```

上游 baseline 变化时按原工作流同步影响；用户要求撤销时只处理本轮相关改动。

## 6. 完成门禁

重新读取全部声明仓库的 staged、unstaged 和 untracked 差异，核对本轮 Txx、完成标准、当前轮次文件、验证、偏差、测试豁免和剩余风险。Full 更新当前 Ixx；Quick 更新对应记录。

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

豁免保留“未验证”事实，不等同验证通过。Full 完成后再运行工作流 `validate`；所有计划 Txx 都完成前不得登记 Review 通过。

最终只报告：完成的 Txx/主链路、关键文件、新鲜验证或豁免、偏差与剩余风险、Ixx 和差异指纹。实现文件、权威输入或后续报告变化时，以状态命令的新鲜度结果为准，不沿用旧结论。
