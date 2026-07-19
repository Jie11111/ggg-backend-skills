# GGG Workflow

`ggg` 是一套给程序员使用的轻量需求工作流，当前覆盖：

`PRD -> 需求对齐 -> 技术方案 -> 任务拆分 -> 编码实现 -> 代码检查 -> 测试验证`

GGG 在测试验证通过后结束；发布、上线、回滚和交付确认由人工负责。

按需补：

- `04-schema.sql`
- 执行态追溯产物：`05-implementation-log.md`、`06-code-review.md`、`07-test-report.md`

## 先记住

- `ggg` 只按阶段显式执行，不自动推进到下一步。
- 只有用户明确点名当前 skill，或明确要求进入当前阶段时，才生成对应文档。
- 所有需求入口先用 `$ggg-prd-intake`，由 GGG 根据需求表达和影响面自动路由 `quick` / `full` 并告知；只有模式冲突或依据不足时才询问。
- `quick` 和 `full` 统一放在 `<项目根目录>/ggg/features/YYYYMMDD-需求名/`。`--repo-root` 指定项目根目录；不传时默认识别当前 Git 仓库根目录，非 Git 目录时使用当前目录。quick 创建轻量 `quick.md`，不创建 `meta.json`；full 创建 `meta.json` 和阶段文档。
- 前置条件不满足时，只说明还缺什么，不先占坑创建下一阶段文档。
- 阶段主文档只允许固定命名：`00-baseline.md`、`01-research.md`、`02-design.md`、`03-tasks.md`、`04-schema.sql`、`05-implementation-log.md`、`06-code-review.md`、`07-test-report.md`。旧需求中的 `01-blocking-issues.md` 必须先合并到 `01-research.md` 再删除。
- `quick.md` 是 quick 轻量记录，不属于 full 阶段主文档，不进入 `meta.json` 状态机和 `00-07` 校验。
- `05-implementation-log.md`、`06-code-review.md`、`07-test-report.md` 是执行态追溯产物，会随着 `编码实现 / 代码检查 / 测试验证` 阶段解锁；review 和 test 支持多轮明细，不覆盖历史轮次。
- `init` 默认只补齐缺失的 `ggg/workflow` README 和模板；如需覆盖刷新，显式加 `--refresh-workflow-assets`。

## 目录结构

```text
ggg/
├─ workflow/
│  ├─ README.md
│  └─ templates/
└─ features/
   └─ YYYYMMDD-需求名称/
      ├─ quick.md                 # quick 使用；full 可保留升级前记录
      ├─ meta.json                # 仅 full
      ├─ 00-baseline.md           # 仅 full
      ├─ 01-research.md
      ├─ 02-design.md
      ├─ interface-details/       # quick / full 均按需
      ├─ 03-tasks.md
      ├─ 04-schema.sql            # quick / full 均按需
      ├─ 05-implementation-log.md
      ├─ 06-code-review.md
      ├─ review-rounds/
      ├─ 07-test-report.md
      ├─ test-rounds/
      └─ assets/
```

## 使用顺序

quick 小需求：

1. `$ggg-prd-intake`：确认 quick 边界、风险和验收信号，创建 / 更新 `quick.md`
2. `$ggg-implementation`：读取 `quick.md`，按 `tiny/normal/high` 选择最小预检，编码后用 `implementation-verify` 把真实命令结果绑定当前代码快照，再由 `implementation-complete` 锁定完成指纹
3. 按需 `$ggg-code-review` / `$ggg-test-verify`：Review 先过 Gate A 再过 Gate B，并覆盖全部 Diff；正式测试从边界、Review、Diff 和副作用生成来源 Manifest，保存可复跑证据。任何输入、代码或报告变化都会使旧结论失效

full 正式需求：

1. `$ggg-prd-intake`
2. `$ggg-requirement-alignment`
3. `$ggg-technical-design`
4. `$ggg-task-breakdown`
5. `$ggg-implementation`
6. `$ggg-code-review`
7. `$ggg-test-verify`

## 每个阶段产出什么

| 阶段 | 输入 | 输出 |
|---|---|---|
| `ggg-prd-intake` | PRD 或一段需求描述，最好顺手给主项目 | 统一 `ggg/features/.../`；quick：`quick.md`；full：`meta.json`、`00-baseline.md` |
| `ggg-requirement-alignment` | 已有 `meta.json`、`00-baseline.md`、当前需求目录 | `01-research.md`，其中统一维护结论、疑问和阻塞问题 |
| `ggg-technical-design` | 已有 `00-baseline.md`、`01-research.md`、当前需求目录 | `02-design.md`，按需补 `interface-details/`、`04-schema.sql`；quick 在实现阶段需要时使用同名产物 |
| `ggg-task-breakdown` | 已确认的 `02-design.md`、当前需求目录 | `03-tasks.md` |
| `ggg-implementation` | full：已确认的 `03-tasks.md`、`02-design.md`、代码事实；quick：`quick.md` | 按风险和任务纵向实现生产代码与必要测试；`implementation-state.json` 锁定仓库、Txx、风险档位、验证命令摘要、实现轮次和差异指纹 |
| `ggg-code-review` | 权威需求/方案、实现证据、当前完整 diff | Gate A 复核需求符合性，Gate B 复核被 Diff 触发的质量风险；CRxx、输入指纹和 Review 工件指纹跨轮次可追溯 |
| `ggg-test-verify` | 通过且新鲜的 Review、验收/规则、真实 diff、测试环境 | `formal-gate / run-only / triage` 三模式；正式门禁输出来源 Manifest、风险场景、Exx 原始证据、Effect/恢复记录和 TVxx 账本 |

## 每个阶段怎么说

### 1. `$ggg-prd-intake`

```text
$ggg-prd-intake
这是 PRD/需求描述：......
主项目先按 xxx 判断。
如果我没说明 quick/full，请先问我这次按小需求快速推进还是正式需求完整流程。
```

quick 示例：

```text
$ggg-prd-intake
这是一个小需求：......
我希望按 quick 快速改，先确认边界和验收信号，在统一 features 目录只初始化 quick.md，不进入 full 状态机。
```

full 示例：

```text
$ggg-prd-intake
这是正式需求：......
请按 full 完整流程澄清并初始化 meta.json 和 00-baseline.md。
```

### 2. `$ggg-requirement-alignment`

```text
$ggg-requirement-alignment
继续这个需求的代码对齐。
重点查清主链路、关键依赖、数据落点和阻塞问题。
当前需求目录：<feature-dir>
```

### 3. `$ggg-technical-design`

前置条件：

- `01-research.md` 已有足够代码证据，且唯一疑问账本已清空

```text
$ggg-technical-design
现在进入技术方案阶段。
请基于当前 baseline 和 research 产出 02-design.md。
如果涉及接口，一个接口一个文档拆到 interface-details。
当前需求目录：<feature-dir>
```

### 4. `$ggg-task-breakdown`

前置条件：

- `02-design.md` 已写实、确认且通过校验

```text
$ggg-task-breakdown
现在基于已确认的 02-design.md 拆 03-tasks.md。
只拆会产生仓库改动的编码任务，按真实代码边界写清所属项目、预计修改文件或符号、编码依赖和完成标准；不要拆发布、人工 SQL、环境配置或测试执行任务。
当前需求目录：<feature-dir>
```

### 5. `$ggg-implementation`

前置条件：

- `03-tasks.md` 已确认
- `02-design.md` 已写实
- 代码落点和验证方式基本明确

```text
$ggg-implementation
现在开始编码实现。
请基于已确认的 03-tasks.md 按任务落代码，代码事实优先；Java 后端改动遵循 ggg-java-coding-standard 和目标项目既有约定。
当前需求目录：<feature-dir>
```

中途有新增澄清时，不单独走阶段；直接在当前阶段按代码事实和用户确认结果调整实现。

### 6. `$ggg-code-review`

前置条件：

- 编码实现已完成
- 本次相关 diff 或文件范围明确
- 已有基础编译、单测、接口验证或明确的验证缺口

```text
$ggg-code-review
请检查本次 Java 后端实现。
先复核代码是否符合需求、代码对齐结论、技术方案、任务拆分、SQL 和接口契约，再检查注释、代码规范、主链路可读性、异常日志、参数校验、SQL/MyBatis、事务、性能、安全、兼容性和测试覆盖。
当前需求目录：<feature-dir>
```

### 7. `$ggg-test-verify`

前置条件：

- 代码检查结论为通过，或用户明确要求带风险验证
- 服务环境、baseUrl 和必要 token 已由用户确认或提供
- 验证范围和报告落点已明确

```text
$ggg-test-verify
请基于本次实现执行测试验证。
优先复用需求目录已有 scripts、联调说明和历史 reports；缺 token 时先说明需要哪类 token。
当前需求目录：<feature-dir>
```

## 最小命令

统一使用 Python 3 和 Codex Home 下的脚本绝对路径，不依赖当前工作目录：

```bash
# 初始化需求目录
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init --repo-root <主项目repo-root> --feature-name <feature-name>

# 初始化 quick 小需求记录，不创建 full 需求目录
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init-quick --repo-root <主项目repo-root> --quick-name <quick-name>

# 如需覆盖刷新共享 README 和模板
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init --repo-root <主项目repo-root> --feature-name <feature-name> --refresh-workflow-assets

# 进入需求对齐
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-alignment --feature-dir <feature-dir>

# 同步状态
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" sync-meta --feature-dir <feature-dir>

# 校验文档
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" validate --feature-dir <feature-dir>

# CodeGraph 无法定位时，仅在已确认的目标项目或模块内扫描候选
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" scan-design-inputs --scope-root <target-project-or-module> --max-files 500 --max-depth 8 --limit 20

# 进入技术方案
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-design --feature-dir <feature-dir>

# 完成 02-design.md 预检后，按需生成 schema
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-design --feature-dir <feature-dir> --create-schema --business-model-confirmed --upstream-contract-confirmed

# 用户确认 SQL 后锁定 04-schema.sql 指纹
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" confirm-schema --feature-dir <feature-dir> --source "<用户确认消息或时间>"

# 进入任务拆分
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-tasks --feature-dir <feature-dir> --design-confirmed

# 进入编码实现
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-implementation --feature-dir <feature-dir> --tasks-confirmed

# 第一处代码修改前开启实现会话；full 可重复传 --task，跨仓重复传 --repo-root
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start --record <quick.md或05-implementation-log.md> --risk-profile <tiny|normal|high> [--task T1] --repo-root <repo1> --repo-root <repo2>

# 接管启动前已经属于本需求的脏文件时逐个声明；单仓可用相对路径，多仓使用绝对路径
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start --record <quick.md或05-implementation-log.md> --repo-root <repo> --adopt-existing-file <已有实现文件>

# 填写当前风险档位要求的最小实现草图后，在第一处新代码修改前锁定预检
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-precheck --record <quick.md或05-implementation-log.md>

# 旧会话已有代码或核心实现草图失效时，保留当前差异并轻量重开下一轮
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-restart --record <quick.md或05-implementation-log.md> --reason "<具体原因>"

# 执行验证并把退出码和输出摘要绑定当前代码快照；命令不经过 shell
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-verify --record <quick.md或05-implementation-log.md> --label unit-test -- <测试命令及参数>

# 填完任务、实际文件和质量证据后，基于真实 Git 差异及新鲜验证锁定完成快照
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-complete --record <quick.md或05-implementation-log.md>

# 确因环境阻塞无法执行时显式记录豁免；已执行且 failed/stale 的结果不能豁免
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-complete --record <quick.md或05-implementation-log.md> --verification-waiver "<具体原因、替代证据与风险>"

# Review 前确认完成后没有继续改代码
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-status --record <quick.md或05-implementation-log.md>

# Review 结束后绑定结论及 fresh/self 方式；self-review 额外传具体降级原因
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" review-mark --record <quick.md或05-implementation-log.md> --result <passed|needs_changes|blocked> --reviewer-mode <fresh-review|self-review> [--self-review-reason "<具体原因>"]

# 兼容旧调用：省略 reviewer-mode 时不会冒充 fresh，会显式降级并记录为 self-review

# 测试前确认 Review 仍有效
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" review-status --record <quick.md或05-implementation-log.md> --require-passed

# 进入代码检查
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-review --feature-dir <feature-dir> --implementation-completed

# 进入测试验证
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-test --feature-dir <feature-dir> --review-passed

# 自动化命令通过无 shell test-run 执行，并绑定 Txx/TSxx、实现和 Review
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-run --record <quick.md或05-implementation-log.md> --round <quick或T1> --scenario <TS1> --environment "<环境与版本>" --effect <read-only|local-write|data-write|state-change|message-or-job|external-side-effect> -- <命令及参数>

# 校验测试场景和证据，并绑定当前实现差异
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-mark --record <05-implementation-log.md> --result passed

# 检查测试结论是否仍然有效
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-status --record <05-implementation-log.md> --require-passed
```

候选扫描不跟随文件或目录符号链接，不输出配置值；被文件上限截断时应缩小范围后重扫。

说明：

- `to-design`、`to-tasks`、`to-implementation`、`to-review`、`to-test`、`complete` 会先执行当前阶段校验，不通过就不会推进。
- `--design-confirmed` 只表示你显式确认方案通过，不再替代文档校验。
- `--tasks-confirmed`、`--implementation-completed`、`--review-passed` 只表示你显式确认上一阶段可以进入下一阶段，不替代文档校验、实现会话状态和差异指纹校验。
- `implementation-precheck` 按 `tiny/normal/high` 只记录当前风险所需的简短实现草图；它必须发生在本轮新增代码修改前。
- `implementation-restart` 只在当前进行中轮次无法继续时使用；它保留现有差异、记录原因并开启下一 Ixx，不修改代码或新增文档。
- `review-mark` 的新调用要求显式记录 `fresh-review / self-review`；历史调用省略时安全降级为 `self-review`。命令校验完整 Diff、Gate A/B、CRxx 连续性和报告中已写明的评审方式，并绑定权威输入与 Review 工件。
- `test-run` 只负责真实执行命令和生成机器证据，不把退出码 0 自动升级成业务场景通过；API 和人工观察仍使用原证据路径。
- `test-mark` 会校验 formal-gate 来源 Manifest、场景、Exx、Effect/恢复、TVxx 和 test-run 机器证据，并把结论绑定当前实现、Review 与测试工件；API 专项报告变化同样会失效。
- 执行态产物由对应 skill 维护；进入 `编码实现 / 代码检查 / 测试验证` 后，`validate` 会检查对应 05/06/07 产物。

## 一句话记忆

先用 `prd-intake` 接住需求并确认 `quick/full`：quick 就落一个 `quick.md`，少文档快速确认边界后交给 `implementation` 定点实现和验证，并按需回写 review / test 结论；full 就继续用 `requirement-alignment` 把需求和代码真正对齐，阻塞清空后写 `technical-design`，方案确认后拆 `task-breakdown`，再用 `implementation` 按任务落代码并记录实现事实，用 `code-review` 做多轮质量门禁，最后用 `test-verify` 生成多轮测试验证结论。
