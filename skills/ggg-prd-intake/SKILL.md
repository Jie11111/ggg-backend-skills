---
name: ggg-prd-intake
description: 需求入口和需求理解阶段。GGG 根据用户表达和影响面推荐 quick/full，但最终模式由用户选择；用户已指定时直接采用，用户授权 AI 决定时记录授权来源。以 PRD、用户消息、会议结论、原型等需求材料为主，必要时只读核实代码事实。高影响阻塞问题一轮一问，同模块低风险独立问题可合并 2-3 个，确认后形成 quick 边界或正式 baseline。仅当用户明确指定 `$ggg-prd-intake`，或要求需求受理、梳理 PRD 基线时使用。
---

# GGG PRD Intake（需求理解）

## 定位与边界

GGG 作为接需求的 Java 程序员，先判断并推荐 `quick/full`，由用户作最终选择，再澄清真正影响业务边界的问题。材料已明确的内容直接记录，不为走流程重复确认。代码现状不等于用户需求，AI 推荐和常见做法也不能替代用户结论。

本阶段优先阅读用户指定的 PRD、消息、会议结论、原型和截图。只有现有系统事实会影响需求理解、提问或推荐时，才只读核实直接相关代码；系统性调用链调研交给 `$ggg-requirement-alignment`，实现选择交给 `$ggg-technical-design`。

- `quick`：在 `ggg/features/YYYYMMDD-小需求名/quick.md` 维护轻量边界，不创建 `meta.json` 和 full 阶段主文档。
- `full`：形成已确认的 `00-baseline.md`，不提前生成 research、design、tasks 或 SQL。
- 跨仓需求只选一个主项目承载文档；真实实现仓库列表单独交给 implementation。

仅在用户明确指定 `$ggg-prd-intake`，或明确要求需求受理、梳理需求基线时执行。

共享资源：

- 脚本：`../ggg-workflow-shared/scripts/workflow_cli.py`
- 提问格式：`../ggg-workflow-shared/references/question-output-template.md`
- quick 模板：`../ggg-workflow-shared/assets/workflow/templates/quick-record-template.md`

## 第一步：推荐 quick / full，由用户选择

AI 推荐不等于用户选择。用户尚未明确模式时只问一次：

```text
推荐使用 quick / full：<一句话依据>。
请确认使用 quick 还是 full。
```

路由规则：

- 用户明确指定 quick/full 时直接采用并记录来源，不重复询问。
- 用户回复“你决定”“按你的建议”等明确授权时，按推荐模式推进并记录“用户授权 AI 决定”及来源。
- 目标单一、范围局部、验收和兼容边界清楚、没有高影响不确定项时，路由 quick。
- 业务闭环较广，或实例身份、核心状态、权限、旧链路副作用、关键契约、数据兼容需要系统对齐时，路由 full。
- SQL、接口或跨项目本身不自动等于 full；只有它们带来高影响不确定性或扩大业务边界时才升级。
- 用户未选择且未授权 AI 决定时，不初始化目录、不创建工件。
- 用户选择与推荐不一致时说明影响，但不得擅自改换模式。
- quick 中发现高影响阻塞或范围扩散时，说明原因并询问是否升级 full；确认前不做越界工作。

quick 只减少产物，不降低反幻觉要求。

## 第二步：按所选模式收口需求

### A. Quick

先收口这些最小边界：

- 一句话目标、改什么、不改什么。
- 主项目、预计代码范围和全部实现仓库。
- 代表性验收例：`前置/输入 → 用户操作或触发 → 系统处理 → 用户可见结果`。
- 涉及状态、幂等、失败或重试时，再补一个失败/重复触发例。
- 兼容性：现有调用方、历史数据、重复请求或重试分别是无影响、有影响还是未知。
- 最小验收信号、剩余风险和升级 full 条件。

代表性验收例只能组合已经明确的规则，不能借例子新增分页、排序、非法值、历史处理等口径；这类细节会改变验收时，必须进入疑问账本。材料已有唯一明确结论时直接记录；需要澄清时使用下文“问题分级”规则。

需求名和主项目明确后初始化：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init-quick \
  --repo-root <项目根目录> \
  --quick-name <小需求名称> \
  --recommended-mode <quick|full> \
  --recommendation-reason "<推荐依据>" \
  --selection-source "<用户选择或授权消息定位>"
```

澄清期间保持 `澄清状态：澄清中`。问题清零后，用一段简短边界复述请用户确认，再改为“已确认”。quick 不生成 `meta.json`、`00-baseline.md`、`01-research.md`、`02-design.md` 或 `03-tasks.md`；后续如确实涉及 SQL 或接口说明，由 implementation 按统一命名创建 `04-schema.sql` 或 `interface-details/`。

完成后显式交给 `$ggg-implementation`，提供 quick 记录绝对路径、全部 Git 仓库根目录、目标、包含/禁止项、代表性验收例、兼容性、验收信号和剩余风险。若用户已在同一轮授权编码，切换并完整加载 implementation 后先执行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" implementation-start \
  --record <quick.md绝对路径> \
  --repo-root <Git仓库1> [--repo-root <Git仓库2> ...]
```

未成功创建 `implementation-state.json` 前不修改代码。

### B. Full

#### 1. 消化材料并建立疑问账本

提炼目标、用户闭环、输入输出、范围、数据身份、状态/重试、旧链路、权限和验收。凡会影响这些基线内容，且材料存在空白、冲突或多种合理解释的事项，都进入疑问账本，不静默补全。

先区分归属：

- `用户意图`：产品语义、业务规则或验收不明，必须由用户确认。
- `代码事实`：只读核实直接相关事实；需要系统调研时转交需求对齐，代码结论不能替代用户意图。
- `设计选择`：业务目标已明确但实现方式未定，转交技术方案。

账本记录：`编号、疑问、问题类型、准确来源、为什么不确定、影响范围、确认人、结论/转交说明、状态`。来源必须可回查；转下游必须写明承接内容，不能用来清理用户意图问题。

需求名和主项目明确后初始化，并保持 `基线状态：澄清中`：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init \
  --repo-root <项目根目录> \
  --feature-name <需求名称> \
  --recommended-mode <quick|full> \
  --recommendation-reason "<推荐依据>" \
  --selection-source "<用户选择或授权消息定位>"
```

#### 2. 问题分级，减少无效往返

- 高影响阻塞：影响目标/范围、角色/权限、业务实例身份、核心状态、旧链路副作用、关键契约/数据兼容、核心验收，或答案会改变其他问题。每轮只问一个。
- 低风险独立：同一模块、彼此无依赖、每项都能独立回答且不影响上述边界。同模块低风险独立问题可以一轮合并 2-3 个，并允许用户部分回答。
- 高影响和低风险不混问；每个账本项仍只确认一个变量。

每项用户可见内容只包含：

- **当前疑问**：必要上下文和一个可独立回答的问题。
- **推荐理解**：明确建议，等待用户确认或纠正；没有可靠依据时写“暂无可靠推荐”。

来源、影响和推荐依据保留在账本，除非用户追问或缺少这些信息会让问题无法理解。用户说“按建议”只代表对当前问题的授权，不得外推。

每轮回答后更新对应项，删除被推翻的判断，检查新冲突并重扫材料；仍有问题时继续按分级规则提问。

#### 3. 清零后只做一次最终确认

问题清零后，确保 baseline 每个关键结论能追溯到 PRD、用户消息或 Qxx。然后用一个具体例子按业务时间顺序反向复述：

```text
用户触发 → 系统自动处理 → 业务实例和关联结果 → 用户最终看到什么
         → 部分失败/重试 → 再次操作 → 历史结果
```

只讲业务语义，不提前设计表、字段或接口。最后只问一次：是否按以上理解形成需求基线；用户纠正则回到疑问账本。

确认后按共享 baseline 模板写清目标、范围、用户闭环、规则、数据身份、旧链路隔离、禁止项和验收标准；原始材料要点登记为 Sxx 并落到基线、Qxx 或明确不适用。然后锁定：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" confirm-baseline \
  --feature-dir <需求目录> --source <用户最终确认消息定位或时间>
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" sync-meta \
  --feature-dir <需求目录>
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" validate \
  --feature-dir <需求目录>
```

validate 通过后进入 `$ggg-requirement-alignment`。需求对齐完成后先确认 SQL 影响；SQL Gate 未满足时不得开始正式技术方案。

## 已确认内容被纠正

- quick：直接更新 `quick.md` 的边界与升级条件，重新做简短边界确认。
- full：先执行同步，撤销受影响的下游门禁：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" sync-clarification \
  --feature-dir <需求目录> --impact baseline \
  --source <用户消息或补充材料> --summary <变化摘要>
```

随后按影响选择确认方式：

- **局部明确修正**：新口径清楚，只影响一个局部规则或结果，能完整列出影响链且没有新高影响疑问。只展示改前、改后、受影响链和明确不受影响的边界，再问一次是否按该差异更新；不重复完整主链路复述。
- **高影响或扩散不明**：涉及目标/范围、实例身份、核心状态、权限、旧链路、关键契约/数据兼容、核心验收，或不能证明影响局部。重新扫描疑问并完成完整反向复述。

两种情况都在用户确认后重新执行 `confirm-baseline`、`sync-meta` 和 `validate`，不能沿用旧指纹。

### Tiny amendment 快速修正

用户明确提出删除单个枚举值、调整文案、补字段注释或补齐日志等局部修正，且影响链能够完整列出时：

- 只更新受影响的基线、SQL 口径、方案、代码和联调文档，不重走完整主链路复述。
- 将修正交给 implementation 的 tiny amendment；使用提交范围或当前增量直接绑定，不重建隔离工作树。
- 默认执行编译、关键字残留检查和 `git diff --check`；不自动创建测试类或触发 Review。
- 发现权限、数据语义、公共契约或 SQL 条件发生扩散时，停止快速路径并回到相应阶段。

## 硬约束与完成标准

- 不因为模板有空位而提问或填充；关键结论没有可回查来源时不能写成已确认。
- 用户意图不能转下游；代码事实和设计选择必须交给正确阶段。
- 不把表、接口、类名或 SQL 等实现设计伪装成需求结论。
- AI 只推荐 quick/full；未记录用户选择或“用户授权 AI 决定”时不得初始化流程。
- full 仍有业务阻塞、关键结论需要猜测或确认未完成时，不进入需求对齐。
- quick 完成时，目标、包含/禁止项、代表性验收例、兼容性、验收信号和升级风险已确认，并已可执行地交给 implementation。
- full 完成时，问题已按影响分级清零，必要反向复述已确认，baseline 来源完整且 `confirm-baseline`、`sync-meta`、`validate` 已通过。
