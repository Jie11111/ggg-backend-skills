# GGG Workflow

`ggg` 是一套给程序员使用的轻量需求工作流，当前覆盖：

`PRD -> 需求对齐 -> 技术方案 -> 任务拆分 -> 编码实现 -> 代码检查 -> 测试验证 -> 交付完成`

按需补：

- `04-schema.sql`
- 执行态追溯产物：`05-implementation-log.md`、`06-code-review.md`、`07-test-report.md`

## 先记住

- `ggg` 只按阶段显式执行，不自动推进到下一步。
- 只有用户明确点名当前 skill，或明确要求进入当前阶段时，才生成对应文档。
- 所有需求入口先用 `$ggg-prd-intake` 确认 `quick` 小需求还是 `full` 正式需求；用户没说时先问，不猜。
- `quick` 小需求不初始化 `ggg/features`，只在主项目仓库根目录创建轻量 `ggg/quick/YYYYMMDD-小需求名/quick.md` 记录边界、风险、实现摘要和验证结论；发现影响面不清时再建议升级 `full`。
- 前置条件不满足时，只说明还缺什么，不先占坑创建下一阶段文档。
- 阶段主文档只允许固定命名：`00-baseline.md`、`01-blocking-issues.md`、`01-research.md`、`02-design.md`、`03-tasks.md`、`04-schema.sql`、`05-implementation-log.md`、`06-code-review.md`、`07-test-report.md`。
- `quick.md` 是 quick 轻量记录，不属于 full 阶段主文档，不进入 `meta.json` 状态机和 `00-07` 校验。
- `05-implementation-log.md`、`06-code-review.md`、`07-test-report.md` 是执行态追溯产物，会随着 `编码实现 / 代码检查 / 测试验证` 阶段解锁；review 和 test 支持多轮明细，不覆盖历史轮次。
- `init` 默认只补齐缺失的 `ggg/workflow` README 和模板；如需覆盖刷新，显式加 `--refresh-workflow-assets`。

## 目录结构

```text
ggg/
├─ workflow/
│  ├─ README.md
│  └─ templates/
├─ quick/
│  └─ YYYYMMDD-小需求名/
│     └─ quick.md
└─ features/
   └─ YYYYMMDD-需求名称/
      ├─ meta.json
      ├─ 00-baseline.md
      ├─ 01-blocking-issues.md
      ├─ 01-research.md
      ├─ 02-design.md
      ├─ interface-details/
      ├─ 03-tasks.md
      ├─ 04-schema.sql
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
2. `$ggg-implementation`：读取 `quick.md`，定位代码、最小实现、自检和局部验证，回写实现摘要
3. 按需 `$ggg-code-review` / `$ggg-test-verify`：读取 `quick.md`，回写 review / 测试结论

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
| `ggg-prd-intake` | PRD 或一段需求描述，最好顺手给主项目 | quick：`ggg/quick/.../quick.md`；full：`meta.json`、`00-baseline.md` |
| `ggg-requirement-alignment` | 已有 `meta.json`、`00-baseline.md`、当前需求目录 | `01-blocking-issues.md`、`01-research.md` |
| `ggg-technical-design` | 已有 `00-baseline.md`、`01-research.md`、当前需求目录 | `02-design.md`，按需补 `interface-details/`、`04-schema.sql` |
| `ggg-task-breakdown` | 已确认的 `02-design.md`、当前需求目录 | `03-tasks.md` |
| `ggg-implementation` | full：已确认的 `03-tasks.md`、`02-design.md`、代码事实；quick：`quick.md` 或用户确认边界 | Java 后端代码、SQL、配置、测试或验证结果；full 按需更新 `05-implementation-log.md`，quick 回写实现摘要 |
| `ggg-code-review` | full：本次相关 `git diff`、`00-baseline.md`、`01-research.md`、`02-design.md`、`03-tasks.md`、`04-schema.sql`、`interface-details/`、代码事实；quick：`quick.md`、diff、代码事实和验证证据 | full：`06-code-review.md`、`review-rounds/review-rNN.md`；quick：回写 `quick.md` Review 结论；结论：通过 / 需修改后通过 / 阻塞 |
| `ggg-test-verify` | full：需求目录、接口文档、测试脚本、token、运行环境；quick：`quick.md`、diff、review 结论和局部验证条件 | full：`07-test-report.md`、`test-rounds/test-rNN.md`、按需 `reports/api-tests/`；quick：回写 `quick.md` 测试结论；结论：通过 / 需补测 / 阻塞 |

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
我希望按 quick 快速改，先确认边界和验收信号，不初始化完整需求目录。
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

- `01-blocking-issues.md` 已清空
- `01-research.md` 已有足够代码证据

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
按程序员可执行任务来拆，写清所属项目、主要落点、前置依赖、输出信号和验收标准。
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

Windows 建议统一用 `py`：

```bash
# 初始化需求目录
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py init --repo-root <主项目repo-root> --feature-name <feature-name>

# 初始化 quick 小需求记录，不创建 full 需求目录
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py init-quick --repo-root <主项目repo-root> --quick-name <quick-name>

# 如需覆盖刷新共享 README 和模板
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py init --repo-root <主项目repo-root> --feature-name <feature-name> --refresh-workflow-assets

# 进入需求对齐
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py to-alignment --feature-dir <feature-dir>

# 同步状态
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py sync-meta --feature-dir <feature-dir>

# 校验文档
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py validate --feature-dir <feature-dir>

# 轻量扫描入口和依赖
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py scan-design-inputs --feature-dir <feature-dir>

# 进入技术方案
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py to-design --feature-dir <feature-dir>

# 进入技术方案并生成 schema
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py to-design --feature-dir <feature-dir> --create-schema --business-model-confirmed --upstream-contract-confirmed

# 进入任务拆分
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py to-tasks --feature-dir <feature-dir> --design-confirmed

# 进入编码实现
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py to-implementation --feature-dir <feature-dir> --tasks-confirmed

# 进入代码检查
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py to-review --feature-dir <feature-dir> --implementation-completed

# 进入测试验证
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py to-test --feature-dir <feature-dir> --review-passed

# 标记交付完成
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py complete --feature-dir <feature-dir> --test-passed
```

说明：

- `to-design`、`to-tasks`、`to-implementation`、`to-review`、`to-test`、`complete` 会先执行当前阶段校验，不通过就不会推进。
- `--design-confirmed` 只表示你显式确认方案通过，不再替代文档校验。
- `--tasks-confirmed`、`--implementation-completed`、`--review-passed`、`--test-passed` 只表示你显式确认上一阶段可以进入下一阶段，不替代文档校验。
- 执行态产物由对应 skill 维护；进入 `编码实现 / 代码检查 / 测试验证 / 交付完成` 后，`validate` 会检查对应 05/06/07 产物是否存在并符合基本结构。

## 一句话记忆

先用 `prd-intake` 接住需求并确认 `quick/full`：quick 就落一个 `quick.md`，少文档快速确认边界后交给 `implementation` 定点实现和验证，并按需回写 review / test 结论；full 就继续用 `requirement-alignment` 把需求和代码真正对齐，阻塞清空后写 `technical-design`，方案确认后拆 `task-breakdown`，再用 `implementation` 按任务落代码并记录实现事实，用 `code-review` 做多轮质量门禁，最后用 `test-verify` 生成多轮测试验证结论。
