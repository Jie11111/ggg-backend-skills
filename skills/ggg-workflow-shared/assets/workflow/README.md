# GGG Workflow

`ggg` 是一套给程序员使用的轻量需求工作流，当前覆盖：

`PRD -> 需求对齐 -> 技术方案 -> 任务拆分 -> 编码实现 -> 测试验证`

代码检查是按需插入的可选动作：只有用户明确要求时才执行一次，不是必经阶段。

GGG 在测试验证通过后结束；发布、上线、回滚和交付确认由人工负责。

按需补：

- `04-schema.sql`
- 执行态追溯产物：`05-implementation-log.md`、`06-code-review.md`、`07-test-report.md`

## 先记住

- `ggg` 只按阶段显式执行，不自动推进到下一步。
- 只有用户明确点名当前 skill，或明确要求进入当前阶段时，才生成对应文档。
- 所有需求入口先用 `$ggg-prd-intake`：AI 推荐 `quick/full` 并说明依据，用户最终选择；用户也可以明确授权 AI 决定。推荐不能代替选择。
- `quick` 和 `full` 统一放在 `<项目根目录>/ggg/features/YYYYMMDD-需求名/`。`--repo-root` 指定项目根目录；不传时默认识别当前 Git 仓库根目录，非 Git 目录时使用当前目录。quick 创建轻量 `quick.md`，不创建 `meta.json`；full 创建 `meta.json` 和阶段文档。
- 前置条件不满足时，只说明还缺什么，不先占坑创建下一阶段文档。
- 阶段主文档只允许固定命名：`00-baseline.md`、`01-research.md`、`sql-draft.sql`、`02-design.md`、`03-tasks.md`、`04-schema.sql`、`05-implementation-log.md`、`06-code-review.md`、`07-test-report.md`。旧需求中的 `01-blocking-issues.md` 必须先合并到 `01-research.md` 再删除。
- `quick.md` 是 quick 轻量记录，不属于 full 阶段主文档，不进入 `meta.json` 状态机和 `00-07` 校验。
- `05-implementation-log.md`、`07-test-report.md` 是实现和测试追溯产物；`06-code-review.md` 只在用户明确要求 Review 时创建。Review 未执行不影响测试。
- 默认不新增或修改测试类；只有用户明确要求测试代码，或需求本身是测试资产时才创建。已有测试可以按需运行。
- 进入技术方案前必须先完成 SQL Gate：查询、DML、DDL 和“无 SQL”都要记录；新版 SQL 工件是 `sql-draft.sql`。
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
      ├─ sql-draft.sql            # 新版 full：技术方案前 SQL Gate
      ├─ 02-design.md
      ├─ interface-details/       # quick / full 均按需
      ├─ 03-tasks.md
      ├─ 04-schema.sql            # quick / 历史 full 按需
      ├─ 05-implementation-log.md
      ├─ 06-code-review.md         # 仅用户明确要求 Review 时创建
      ├─ 07-test-report.md
      ├─ test-rounds/
      └─ assets/
```

## 使用顺序

quick 小需求：

1. `$ggg-prd-intake`：确认 quick 边界、风险和验收信号，创建 / 更新 `quick.md`
2. `$ggg-implementation`：读取 `quick.md`，按 `tiny/normal/high` 选择最小预检；默认不写测试类，同轮完成精度、字段注释、异常、日志和 Trace
3. 按需 `$ggg-code-review` / `$ggg-test-verify`：Review 仅在用户明确要求时执行，只看需求偏差、代码质量和格式；没有 Review 也可直接测试

full 正式需求：

1. `$ggg-prd-intake`
2. `$ggg-requirement-alignment`：本阶段内完成 SQL Gate；无 SQL也明确登记，有 SQL 则确认 `sql-draft.sql`
3. `$ggg-technical-design`
4. `$ggg-task-breakdown`
5. `$ggg-implementation`
6. 按需 `$ggg-code-review`（用户未要求时跳过本阶段，不登记 skip）
7. `$ggg-test-verify`（可从编码实现直接进入）

## 每个阶段产出什么

| 阶段 | 输入 | 输出 |
|---|---|---|
| `ggg-prd-intake` | PRD 或一段需求描述，最好顺手给主项目 | 统一 `ggg/features/.../`；quick：`quick.md`；full：`meta.json`、`00-baseline.md` |
| `ggg-requirement-alignment` | 已有 `meta.json`、`00-baseline.md`、当前需求目录 | `01-research.md`；识别 SQL 影响，并在有 SQL 时准备 `sql-draft.sql` 供用户确认 |
| `ggg-technical-design` | 已闭合的 baseline、research 和 SQL Gate | `02-design.md`，其中 `接口设计` 使用固定七列表；按需补 `interface-details/` |
| `ggg-task-breakdown` | 已确认的 `02-design.md`、当前需求目录 | `03-tasks.md` |
| `ggg-implementation` | full：已确认的 `03-tasks.md`、`02-design.md`、代码事实；quick：`quick.md` | 纵向实现生产代码；默认不写测试类，同轮处理精度、字段注释、异常、日志、Trace，并锁定差异指纹 |
| `ggg-code-review` | 权威需求/方案、实现证据、当前 diff | 仅用户明确要求时生成一份可选 Review，检查需求偏差、代码质量与格式 |
| `ggg-test-verify` | 验收/规则、真实 diff、实现证据、测试环境，以及可选 Review 结论 | `formal-gate / run-only / triage`；命令通过一次性非 PTY 进程执行并保存证据 |

## 每个阶段怎么说

### 1. `$ggg-prd-intake`

```text
$ggg-prd-intake
这是 PRD/需求描述：......
主项目先按 xxx 判断。
请先推荐 quick 或 full 并说明依据，最终由我选择；不要把推荐直接当成选择。
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
重点查清主链路、关键依赖、数据落点、SQL 影响和阻塞问题。
进入技术方案前，先让我确认“无 SQL”或 sql-draft.sql 中的精确 SQL。
当前需求目录：<feature-dir>
```

### 3. `$ggg-technical-design`

前置条件：

- `01-research.md` 已有足够代码证据，且唯一疑问账本已清空
- SQL Gate 已完成：`none/query_dml/ddl` 已登记并保持指纹有效

```text
$ggg-technical-design
现在进入技术方案阶段。
请基于当前 baseline、research 和已确认 SQL 产出 02-design.md，不要在方案中第一次设计 SQL。
如果涉及接口，一个接口一个文档拆到 interface-details。
接口总览使用“接口设计”七列表头。
当前需求目录：<feature-dir>
```

### 4. `$ggg-task-breakdown`

前置条件：

- `02-design.md` 已写实、确认且通过校验

```text
$ggg-task-breakdown
现在基于已确认的 02-design.md 拆 03-tasks.md。
只拆会产生仓库改动的编码任务，按真实代码边界写清所属项目、预计修改文件或符号、编码依赖和完成标准；不要拆发布、人工 SQL、环境配置或测试执行任务。
默认不要创建测试类任务；只有我明确要求测试代码时才纳入。
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
请基于已确认的 03-tasks.md 按任务落代码，代码事实优先，遵循 Java 后端代码规范和作者个人风格。
默认不创建或修改测试类；同轮检查大整数精度、请求/响应字段注释、异常、日志和 Trace。
当前需求目录：<feature-dir>
```

中途有新增澄清时，不单独走阶段；直接在当前阶段按代码事实和用户确认结果调整实现。

### 6. `$ggg-code-review`

前置条件：

- 编码实现已完成
- 本次相关 diff 或文件范围明确
- 已有基础编译、静态检查、接口验证、已有测试或明确的验证缺口

```text
$ggg-code-review
请检查本次实现：一看代码是否偏离已确认需求，二看代码质量和项目格式是否合格。
只做一次轻量检查并列出具体文件行号；不要创建评审包、双 Gate 或多轮问题账本。
当前需求目录：<feature-dir>
```

### 7. `$ggg-test-verify`

前置条件：

- 编码实现已完成且当前差异明确；Review 不是前置条件
- 服务环境、baseUrl 和必要 token 已由用户确认或提供
- 验证范围和报告落点已明确

```text
$ggg-test-verify
请基于本次实现执行测试验证。
优先复用需求目录已有 scripts、联调说明和历史 reports；缺 token 时先说明需要哪类 token。
命令使用一次性非 PTY 进程，默认 60 秒；不要启动常驻脱敏终端。
当前需求目录：<feature-dir>
```

## 最小命令

统一使用 Python 3 和 Codex Home 下的脚本绝对路径，不依赖当前工作目录：

```bash
# 初始化 full 需求目录；selection-source 必须定位到用户选择或用户授权 AI 决定
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init \
  --repo-root <主项目repo-root> --feature-name <feature-name> \
  --recommended-mode <quick|full> \
  --recommendation-reason "<推荐依据>" \
  --selection-source "<用户选择 full 或授权 AI 决定的消息定位>"

# 初始化 quick 小需求记录，不创建 full 状态机
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init-quick \
  --repo-root <主项目repo-root> --quick-name <quick-name> \
  --recommended-mode <quick|full> \
  --recommendation-reason "<推荐依据>" \
  --selection-source "<用户选择 quick 或授权 AI 决定的消息定位>"

# 如需覆盖刷新共享 README 和模板
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init \
  --repo-root <主项目repo-root> --feature-name <feature-name> \
  --recommended-mode full --recommendation-reason "<推荐依据>" \
  --selection-source "<用户选择 full 的消息定位>" --refresh-workflow-assets

# 进入需求对齐
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-alignment --feature-dir <feature-dir>

# 同步状态
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" sync-meta --feature-dir <feature-dir>

# 校验文档
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" validate --feature-dir <feature-dir>

# CodeGraph 无法定位时，仅在已确认的目标项目或模块内扫描候选
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" scan-design-inputs --scope-root <target-project-or-module> --max-files 500 --max-depth 8 --limit 20

# 在需求对齐阶段先确认 SQL Gate；无 SQL 也执行，涉及 SQL 时先填写 sql-draft.sql
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" confirm-sql \
  --feature-dir <feature-dir> --source "<用户确认消息或时间>"

# SQL Gate 有效后进入技术方案
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-design --feature-dir <feature-dir>

# 历史流程继续使用 04-schema.sql / confirm-schema，不自动迁移
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" confirm-schema \
  --feature-dir <legacy-feature-dir> --source "<用户确认消息或时间>"

# 进入任务拆分
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-tasks --feature-dir <feature-dir> --design-confirmed

# 进入编码实现
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-implementation --feature-dir <feature-dir> --tasks-confirmed

# 第一处代码修改前开启实现会话；full 可重复传 --task，跨仓重复传 --repo-root
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start --record <quick.md或05-implementation-log.md> --risk-profile <tiny|normal|high> [--task T1] --repo-root <repo1> --repo-root <repo2>

# 接管启动前已经属于本需求的脏文件时逐个声明；单仓可用相对路径，多仓使用绝对路径
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start --record <quick.md或05-implementation-log.md> --repo-root <repo> --adopt-existing-file <已有实现文件>

# 已提交实现直接绑定提交范围，不重建历史 worktree
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start \
  --record <quick.md或05-implementation-log.md> --risk-profile tiny \
  --repo-root <repo> --diff-range <BASE>..<TARGET>

# 单个普通提交可直接接管
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start \
  --record <quick.md或05-implementation-log.md> --risk-profile tiny \
  --repo-root <repo> --adopt-commit <COMMIT>

# 填写当前风险档位要求的最小实现草图后，在第一处新代码修改前锁定预检
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-precheck --record <quick.md或05-implementation-log.md>

# 旧会话已有代码或核心实现草图失效时，保留当前差异并轻量重开下一轮
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-restart --record <quick.md或05-implementation-log.md> --reason "<具体原因>"

# 一次性非 PTY 执行验证；默认 60 秒，超时回收完整进程组
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-verify --record <quick.md或05-implementation-log.md> --label compile --timeout-seconds 60 -- <验证命令及参数>

# 填完任务、实际文件和质量证据后，基于真实 Git 差异及新鲜验证锁定完成快照
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-complete --record <quick.md或05-implementation-log.md>

# 确因环境阻塞无法执行时显式记录豁免；已执行且 failed/stale 的结果不能豁免
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-complete --record <quick.md或05-implementation-log.md> --verification-waiver "<具体原因、替代证据与风险>"

# Review 前确认完成后没有继续改代码
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-status --record <quick.md或05-implementation-log.md>

# 用户明确要求 Review 时，登记单一的两项检查结论
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" review-mark \
  --record <quick.md或05-implementation-log.md> --result <passed|needs_changes|blocked>

# 只有用户明确要求 Review 时才进入代码检查并创建一份简洁工件
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-review \
  --feature-dir <feature-dir>

# 进入测试验证；实现完成后可直接执行，不要求先做 Review
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-test --feature-dir <feature-dir>

# 自动化命令通过无 shell test-run 执行，并绑定 Txx/TSxx 和当前实现
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-run --record <quick.md或05-implementation-log.md> --round <quick或T1> --scenario <TS1> --environment "<环境与版本>" --effect <read-only|local-write|data-write|state-change|message-or-job|external-side-effect> [--timeout-seconds 60] -- <命令及参数>

# 校验测试场景和证据，并绑定当前实现差异
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-mark --record <05-implementation-log.md> --result passed

# 检查测试结论是否仍然有效
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-status --record <05-implementation-log.md> --require-passed
```

候选扫描不跟随文件或目录符号链接，不输出配置值；被文件上限截断时应缩小范围后重扫。

说明：

- `to-design`、`to-tasks`、`to-implementation`、`to-review`、`to-test`、`complete` 会先执行当前阶段校验，不通过就不会推进。
- `--design-confirmed` 只表示你显式确认方案通过，不再替代文档校验。
- `--tasks-confirmed` 只表示你显式确认上一阶段可以进入下一阶段，不替代文档校验、实现会话状态和差异指纹校验。`to-review` 和 `to-test` 都直接读取实现完成状态。
- `implementation-precheck` 按 `tiny/normal/high` 只记录当前风险所需的简短实现草图；它必须发生在本轮新增代码修改前。
- `implementation-restart` 只在当前进行中轮次无法继续时使用；它保留现有差异、记录原因并开启下一 Ixx，不修改代码或新增文档。
- `review-mark` 只登记一份可选 Review 的两项检查结论；没有 Review 时无需执行任何 Review 命令。
- `test-run` 使用一次性非 PTY 进程，默认 60 秒；超时先 TERM、再 KILL 整个进程组并记录回收事实。退出码 0 不自动升级成业务场景通过。
- `test-mark` 会校验 formal-gate 来源 Manifest、场景、Exx、Effect/恢复、TVxx 和 test-run 机器证据，并把结论绑定当前实现与测试工件；API 专项报告变化同样会失效。
- 执行态产物由对应 skill 维护；`validate` 检查实现和测试产物。可选 Review 的两项内容只在 `review-mark` 时校验，不参与通用流程门禁。

## 一句话记忆

先由 AI 推荐、用户选择 `quick/full`。quick 用 `quick.md` 快速锁定边界后定点实现；full 在 `requirement-alignment` 中清空疑问并先确认 SQL，再写技术方案和固定七列接口设计、拆任务、实现。默认不写测试类；Review 仅用户要求时执行且不阻塞测试，最后按需用一次性测试进程验证。
