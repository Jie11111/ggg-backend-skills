---
name: ggg-test-verify
description: 测试验证阶段。GGG 在代码检查通过后，从验收目标、业务规则、Review 缺口和真实代码差异生成完整测试来源清单，按风险设计场景并保存可复跑的执行证据；正式结论绑定当前实现、Review 和测试工件，代码或报告变化后自动失效。用户要求正式验收本次改动、只运行指定测试、定位测试失败或生成测试报告时使用。
---

# GGG Test Verify（测试验证）

## 定位

证明本次业务行为是否满足已确认要求，不重复评审代码风格，不在测试阶段顺手修改业务代码或测试代码。发现实现或测试资产缺失时返回 `$ggg-implementation`。

发布、上线、回滚和交付确认由人工负责；测试通过不等于已发布或可以直接上线。

## 模式

- `formal-gate`：正式验收本次实现；要求当前 Review 通过，维护测试轮次，只有该模式可以执行 `test-mark`。
- `run-only`：只运行指定命令、测试集或接口；报告局部观察，不声明整体通过。
- `triage`：定位失败；可在 Review 无效或环境异常时使用，不登记正式通过。

“验证本次改动”“开始测试”“生成正式报告”默认 `formal-gate`；明确只运行某项测试时用 `run-only`；排查失败时用 `triage`。模式和切换原因必须入档。

## 硬约束

- 未执行写 `未执行`，失败写 `失败`；不得用“已验证”掩盖结果。
- `formal-gate` 必须完整枚举测试来源；每项来源要映射场景，或记录不适用/豁免的事实、授权和剩余风险。
- 关键场景必须有可观察预期和可复跑证据；失败、阻塞或未执行时不能通过。
- 可执行的自动化命令必须通过 `test-run` 运行并生成机器证据；不得手写 `command:` 执行记录或用任意文件哈希冒充命令执行。
- 执行证据必须绑定场景、命令/请求、cwd、环境、时间、退出码/响应、证据位置与摘要。
- 涉及数据写入、状态改变、消息/任务或外部调用时，执行前声明 effect、影响与恢复方式；线上默认只读，线上副作用必须经用户明确授权。
- token、Cookie、密码、Authorization 和业务敏感数据必须脱敏。
- “用户未要求写测试”不是接受关键覆盖缺口的理由。
- 高风险测试来源必须标记为必测并映射关键场景；未执行或豁免时只能登记需补测/阻塞，不能登记正式通过。
- 开始和登记前都确认 Review 仍绑定当前实现；代码或测试工件变化后旧结论失效。

## 输入与工件

- Full：读取 `00-baseline.md` 至 `06-code-review.md`、`implementation-state.json`、相关轮次、契约/SQL、当前真实 diff、现有测试和环境事实。
- Quick：读取 `quick.md`、相关契约/SQL、当前 diff、Review 结论和可用验证命令。
- Full 输出 `07-test-report.md`、`test-rounds/test-rNN.md`；通用原始证据放 `reports/test-evidence/`，接口专项证据可放 `reports/api-tests/`，并纳入本轮证据清单。
- 历史报告只能复用方法，不能复用“通过”结论；环境、版本、账号和数据必须重新确认。

## 流程

### 1. 锁定模式和基线

`formal-gate` 先执行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" review-status \
  --record <quick.md或05-implementation-log.md> --require-passed
```

失败时停止正式门禁；需要诊断则切换 `triage`。Full 尚未进入测试阶段时执行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-test \
  --feature-dir <feature-dir> --review-passed
```

执行测试前按模板创建轮次，冻结实现轮次、差异指纹、Review 轮次、环境、模式和 effect 边界；禁止事后凭记忆补计划。

### 2. 生成完整来源 Manifest

枚举 TBxx：全部验收结果/禁止项、改变的规则/状态/权限、Review 验证缺口、diff 外部行为与副作用、受影响兼容边界，以及被本次变更触发的 NFR。

同一业务结果可合并多个来源定位，但不能丢来源。每个 TBxx 都要记录风险、是否必测、effect、覆盖场景或不适用/豁免依据。业务意图仍不清时路由需求入口/对齐，不自行补需求。

### 3. 设计风险驱动场景

按严重度、发生可能性和可探测性选择场景级别、验证类型和执行顺序；先验证一旦失败会使后续证据失真的前置条件和最高风险行为。最低覆盖与 effect 定义见 [risk-driven-testing.md](references/risk-driven-testing.md)。

场景用业务语言描述可准备的前置、具体操作/数据、可观察预期和 effect。核心规则、状态、权限、公共契约、SQL/事务或异步副作用缺少必要自动化/契约验证时，记录缺口并返回 `$ggg-implementation`；明确豁免时保留授权、替代证据和残余风险。

### 4. 执行并固化证据

可执行命令使用统一入口；命令不经过 shell，执行前校验当前实现、Review、测试轮次、TSxx 和 Effect，随后自动写入 Exx、脱敏证据及 SHA-256：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-run \
  --record <quick.md或05-implementation-log.md> \
  --round <quick或T1> \
  --scenario <TS1> \
  --environment "<本地/CI与关键版本>" \
  --effect <read-only|local-write|data-write|state-change|message-or-job|external-side-effect> \
  [--cwd <已声明仓库内目录>] \
  [--effect-authorization "<副作用授权定位>"] \
  -- <命令及参数>
```

API 专项报告和人工观察不强制转换成 CLI 命令，分别在执行记录使用 `api:`、`observation:`，继续记录脱敏请求/观察点、协议结果、环境、回查位置和真实证据文件。命令使用 `command:`，只能由 `test-run` 自动写入。退出码 0 只证明命令和其中的自动化断言成功；仍需核对业务结果与副作用，再填写 TSxx 场景结论。

每次实际执行新增 Exx 并关联 TSxx，记录 cwd/环境/版本、时间、退出码或协议结果、输出/日志/响应/回查位置、证据 SHA-256 和实际 effect。可保存的原始证据统一落到 feature 的 `reports/` 下；不能保存文件时记录原因及足以复查的脱敏摘要。

HTTP 200、退出码 0 或编译成功不能单独证明业务成功；必须同时核对业务结果和必要副作用。产生写入或状态变化后记录清理、恢复或最终状态回查。

### 5. 失败归因和路由

区分事实与推测，每个失败只选一个主要归因：

| 归因 | 返回位置 |
|---|---|
| 需求歧义 | 需求入口 / 需求对齐 |
| 方案遗漏 | 技术方案 |
| 实现偏差 | `$ggg-implementation` |
| 测试用例偏差 | 修正测试资产并重开测试轮次 |
| 环境/数据问题 | 保持阻塞或继续 `triage` |
| 覆盖不足 | 补场景；需改代码时返回 `$ggg-implementation` |

记录归因证据、影响的 TBxx/TSxx、目标阶段和复验条件；测试阶段不顺手修代码。

### 6. 收口轮次和结论

Full 复测新增 `test-rNN.md`，不覆盖历史；继承全部未关闭 TVxx，原编号不变，关闭时提供本轮证据。Quick 回写轻量场景，复杂证据另存专项报告。

`formal-gate` 结论只允许：

- `通过`：必测来源全部覆盖、关键场景通过、无失败/阻塞，effect 已恢复或回查；
- `需补测`：未发现实现失败，但仍缺一般场景、环境证据或低风险回归；
- `阻塞`：关键场景失败/未执行、来源未闭合，或基线、环境、数据无法判断。

`run-only` 和 `triage` 只报告观察与未知。登记 `formal-gate` 前再次执行 `review-status --require-passed`，然后：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-mark \
  --record <quick.md或05-implementation-log.md> \
  --result <passed|needs_more|blocked>
```

测试工件指纹只由 `test-mark` 写入 `implementation-state.json`；报告不回填、不自报绑定状态。确认结论仍有效：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" test-status \
  --record <quick.md或05-implementation-log.md> --require-passed
```

## 完成条件

- `formal-gate`：来源完整、关键风险有证据、effect 和 TVxx 闭合，且 `test-mark` 成功。
- `run-only`：指定测试已执行或给出可复现阻塞，没有扩大结论。
- `triage`：主要归因、事实证据、目标阶段和复验条件明确。
