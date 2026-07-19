---
name: ggg-code-review
description: 代码检查阶段。GGG 优先使用无 implementation 历史的 fresh-context 评审者，把当前完成快照冻结为 Review 输入；fresh 能力不可用时显式降级为 self-review。先执行需求符合性 Gate A，再按真实 diff 风险执行代码质量 Gate B；结论覆盖全部差异文件并绑定评审方式、实现轮次、实现差异指纹、Review 输入指纹和 Review 工件指纹。用于用户明确指定 `$ggg-code-review`，或要求检查代码、本轮实现复查、quick 改动复查、看看还有没有问题时。
---

# GGG Code Review

## 定位

判断本轮实现是否“实现了正确的内容”，再判断“实现质量是否足以进入测试”。默认只评审不修复；需要修改时，记录 CRxx 后回到 `$ggg-implementation` 开启新实现轮次，代码变化后重新 Review。

有效 Review 必须满足：

- Gate A `Spec Compliance` 先于 Gate B `Code Quality`。
- 优先由无 implementation 历史的 fresh-context 评审者读取权威口径和原始 diff；不可用时显式记录 `self-review` 及原因。
- 先形成评审判断，才能把 implementation 自检作为交叉线索。
- 全部真实 diff 文件逐项覆盖；指定文件只是入口，不得缩小必要影响面。
- 结论绑定实现轮次、实现差异指纹、Review 输入指纹和由状态机计算的 Review 工件指纹。
- CRxx 全局单调递增且 append-only；复审只更新状态和关闭依据，不删除或复用编号。

## 读取资源

- Java 后端改动：读取 `../ggg-java-coding-standard/SKILL.md`。
- 执行 Gate B：读取 `references/code-review-quality-checklist.md`，只加载被 diff 触发的风险模块。
- full：读取 baseline、research、design、tasks、SQL、接口明细、实现记录和历史 Review。
- quick：读取 `quick.md`、同目录按需产物、实现状态和历史 Review 结论。
- 始终读取 Git 已暂存、未暂存、未跟踪文件及必要直接上下游。

权威顺序：用户最新确认/PRD → baseline 或 quick 边界 → research/design/tasks/契约 → 代码与运行事实。派生文档冲突时记录应回写位置；业务口径无法确定时阻塞，不用推断补齐。

## 执行流程

### 1. 冻结 Review 输入

先执行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-status \
  --record <quick.md或05-implementation-log.md>
```

实现未完成、状态缺失或差异指纹失效时，返回 implementation，不产生有效 Review。

full 仍在编码实现阶段时执行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-review \
  --feature-dir <feature-dir> --implementation-completed
```

建立 Review Package：

1. 固定对应实现轮次和实现差异指纹。
2. 枚举全部真实 diff 路径及变更类型，包含未跟踪新文件。
3. 记录权威输入文件及 digest，生成 Review 输入指纹。
4. 标记每个 diff 文件的来源、行为影响、风险标签和所需证据。
5. 先形成独立判断，再读取 implementation 自检交叉核对；自检不是通过证据。

无关需求、生成噪音或大面积历史清理应先拆分。任何 diff 文件未进入覆盖清单时不得通过。

### 1.1 选择评审上下文

- 能启动 subagent 或 fresh thread 时，使用无历史上下文的 reviewer（例如 `fork_turns="none"`）；只提供冻结的 Review Package、权威需求工件、完整 diff 和必要代码入口，不传实现讨论、预期结论或当前 Agent 的诊断。
- fresh reviewer 负责 Gate A、Gate B、CRxx 和 Review 报告；协调 Agent 只运行确定性登记，不改写 reviewer 的发现。
- fresh 能力不可用或启动失败时，直接降级为 `self-review` 并记录具体原因，不增加用户确认轮次。
- `self-review` 可以继续门禁，但不得表述为“独立评审”；最终回复必须明确说明本轮评审方式。

### 2. Gate A：Spec Compliance

按真实用户路径和必要影响面回答：

1. 是否存在需求要求但未实现的行为。
2. 是否存在已实现但语义、边界或副作用错误的行为。
3. 是否存在超出确认范围的行为。
4. 接口、身份、权限、状态、SQL、事务、数据迁移及兼容性是否偏离确认口径。
5. 文档承诺、代码行为和“已验证”声明是否都有独立证据；未查证不得写成不存在。

full 逐项覆盖 Bxx/Cxx/Dxx/Txx 和按需接口、SQL；quick 覆盖目标、禁止项及每个 diff 文件的来源。局部类名或分层不同但行为正确不构成问题。

Gate A 只允许 `通过 / 需修改 / 阻塞`。未通过时记录 CRxx 并返回 implementation；可停止常规 Gate B，但已发现的安全、数据破坏等高风险问题仍须记录。

### 3. Gate B：Risk-driven Code Quality

Gate A 通过后，按 checklist 执行：

- 始终检查正确性、安全与权限、数据一致性、失败边界、兼容性、验证充分性。
- 根据 diff 触发 API、SQL/事务、DDL/迁移、MQ/异步、缓存/ES、配置/依赖、性能/可观测性、前端等模块。
- formatter、lint、编译、静态扫描和已有测试使用真实命令证据；不能由模型手填“通过”替代。
- 没有新增测试本身不是问题；高风险行为缺少自动化测试或明确豁免依据时属于验证缺口。

只记录影响正确性、安全、兼容、可维护性或后续修改安全的问题，不把个人偏好和无关历史坏味道列为本轮必须修。

### 4. 问题连续性与复审

- 新问题使用下一个 CRxx，不按轮次重新编号。
- 新轮次继承全部历史未关闭 CRxx，并记录本轮状态、实现轮次和关闭证据。
- `fixed` 必须由新 diff 和复审证据支持；风险接受仅适用于用户有权接受且不违反硬约束的事项。
- 代码、SQL、配置或测试发生任何变化后，旧 Review 立即失效；重新完成 implementation 并生成新的 Review Package。

### 5. 写入结论并绑定

full 新增 `review-rounds/review-rNN.md`，更新 `06-code-review.md`；quick 回写 `quick.md` 的两门 Gate、完整 diff 覆盖和问题。先完成全部报告内容，再执行登记；Review 工件指纹只由 `review-mark` 写入 `implementation-state.json`，报告不回填、不自报该指纹。

报告已经明确写出的 `fresh-review / self-review` 及原因是权威来源；登记命令只补模板占位，不得覆盖冲突内容。

最终结论：

- `通过`：Gate A、Gate B 均通过，没有未关闭的阻塞或必须修问题，全部 diff 已覆盖。
- `需修改`：存在必须修问题或重要验证缺口。
- `阻塞`：需求、接口、表结构、安全、数据一致性或运行事实无法确认。

最后执行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" review-mark \
  --record <quick.md或05-implementation-log.md> \
  --result <passed|needs_changes|blocked> \
  --reviewer-mode <fresh-review|self-review> \
  [--self-review-reason "<仅 self-review 必填的具体原因>"]
```

命令失败或任一指纹与当前状态不一致时，本轮结论不得生效。通过时只需报告评审方式、结论、CRxx、剩余风险和未覆盖验证；没有问题则明确说明未发现需要修改的问题。只有 `fresh-review` 可以称为独立评审。

登记后只读确认：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" review-status \
  --record <quick.md或05-implementation-log.md> [--require-passed]
```

此后修改需求输入、实现证据、Review 报告、SQL、配置、代码或测试代码，旧 Review 都会失效；不要为回填字段修改已登记报告。

## 门禁

- `implementation-status` 成功，Review Package 完整且没有漏评 diff。
- Gate A 先通过，Gate B 的核心面和所有触发模块均有独立证据。
- 全部 CRxx 连续可追溯，阻塞/必须修问题已关闭。
- `review-mark` 成功，结论绑定当前实现快照及两类 Review 指纹。
