---
name: ggg-technical-design
description: 技术方案阶段。GGG 只在需求、代码事实和 SQL Gate 均已闭合后编写可直接实现的 Java 后端方案，覆盖持久或无持久实例、HTTP/RPC/MQ/Job 契约、数据承载、已确认 SQL、真实代码落点和验证风险，并维护统一接口设计索引。仅当用户明确指定 `$ggg-technical-design` 或明确要求开始、编写或调整技术方案时使用。
---

# GGG Technical Design（技术方案）

## 定位

把已确认的 `00-baseline.md` 和 `01-research.md` 转成可实现、可评审的 `02-design.md`。本阶段不写业务代码，不生成 `03-tasks.md`。

遵守三条主线：

- 保持 `Cxx → Dxx → Txx`：Cxx 提供事实，Dxx 记录实现决策，后续 Txx 承接 Dxx。
- 默认复用现有能力和最小改动；新表、新接口、新服务、中间件、锁或抽象层必须有当前约束。
- `Dxx` 是“当前事实、最小方案、复杂备选、取舍、升级条件和验证方式”的唯一真相；其他章节只引用 Dxx，不重复维护同一决策。

共享资源：

- 工作流脚本：`${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py`
- 技术方案模板：`${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/assets/workflow/templates/technical-design-template.md`
- 接口明细模板：`${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/assets/workflow/templates/interface-detail-template.md`
- SQL 条件化检查：`references/sql-design-checklist.md`
- 契约与接口明细条件：`references/contract-detail-checklist.md`

## 前置条件

- 需求对齐已完成且 validate 通过。
- `01-research.md` 没有未解决的阻塞问题。
- 业务目标、验收标准和关键代码事实足以作出设计。
- SQL Gate 已满足：不涉及 SQL，或 `sql-draft.sql` 已由用户确认且当前语义指纹有效。

条件不满足时只列缺口，不开始方案。

## 执行步骤

### 1. 进入技术方案

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-design --feature-dir <需求目录>
```

读取 baseline、research 和当前 v5 模板。不要另建常态设计工件。

### 2. 记录输入去向

在 §0 逐项登记所有可用于设计的 Cxx 和转交设计的 Qxx，每个输入只出现一次：

- 进入设计：指向 Dxx 或具体章节。
- 仅作为风险：指向风险落点。
- 不进入设计：写明原因。
- 设计选择 Qxx：必须形成 Dxx。

§0 只记录输入 ID、处理方式和去向，不复制 Research 摘要。

### 3. 先确定身份、契约和数据承载

#### 实例身份与可信边界

- 存在持久业务实例时，说明唯一标识、状态隔离、去重、生命周期、身份来源和可信边界。
- 不存在持久业务实例时，明确写“无持久业务实例”及原因；仍说明调用方身份、权限和不可由外部伪造的字段。
- 不把前端或上游不可信的关键身份字段直接作为普通入参使用。

#### 调用方与接口契约

统一按触发方式描述，不假设一定有页面：

- HTTP：页面、第三方或服务调用。
- RPC：Facade/Dubbo/内部服务调用。
- MQ：事件生产与消费。
- Job：定时、补偿或批处理触发。

写清调用方、触发动作、契约类型与标识、关键输入、后端推导字段及可信来源、禁止外部传字段、输出字段或副作用、兼容要求和来源 Cxx/Dxx。主表与独立明细必须对这些字段逐项精确闭环；涉及新增或修改契约时读取 `references/contract-detail-checklist.md`。

#### 数据承载

说明实际选用的 MySQL、Redis、ES、MQ、配置或本地缓存分别承载什么，以及一致性、生命周期、幂等和失败处理。未选择非 MySQL 载体时删除对应承载明细，不再写一行重复的“不涉及”。

### 4. 完成设计决策与代码落点

每个影响实现的关键选择登记为 Dxx，并至少引用一个有效 Cxx。Dxx 必须写清：

- 当前事实或约束。
- 最小可行方案。
- 更复杂备选及不采用原因。
- 影响或代价。
- 触发升级条件。
- 验证方式。

随后完成：

- 核心改动：使用真实项目、类、方法、表、配置或 Topic，不发明代码落点；每条改动至少引用一个承载它的 Dxx。
- 调用链：说明调用方、被调方和关键对象。
- 写链路：说明事务、幂等、状态流转、异常和补偿边界。
- 影响范围、兼容要求、测试链路和关键风险。

只有跨系统、异步链路或复杂事务需要主时序图；普通单服务链路写清调用链即可，并注明不画图原因。

### 5. 引用已确认 SQL

技术方案不得在本阶段第一次设计 SQL。读取 `01-research.md` 的 SQL Gate 和已确认的 `sql-draft.sql`：

- `02-design.md` 只说明 SQL 的业务理由、真实代码落点、事务/并发、兼容、回滚和验证，并引用确认来源与语义指纹。
- 查询或 DML 必须保持已确认的表、JOIN、字段、过滤、排序、分页和更新条件。
- DDL 必须保持已确认的字段类型、默认值、主键、索引、约束和完整结构。
- 仅别名、空白和格式变化不触发重新确认；任何 SQL 语义变化必须先执行 `sync-clarification --impact sql design tasks`，回到 SQL Gate。若代码调研结论本身也变化，再同时加入 `research`。历史需求仍按原 `schema` 影响项兼容处理。
- 旧需求仍可继续使用已确认的 `04-schema.sql`；新需求以 `sql-draft.sql` 为 SQL 唯一真相。

### 6. 维护接口设计和按需明细

在 `02-design.md` 的“八、接口设计”中维护唯一接口索引，表头固定为：

```markdown
| 接口名称 | 新增/修改 | 请求方式 | 路径/方法 | 所属项目 | 接口文档地址 | 备注 |
|---|---|---|---|---|---|---|
```

§三只负责调用方、可信字段和契约边界，§八只负责接口索引，不重复参数细节。

只有外部、公共或复杂契约需要 `interface-details/`：

- 跨团队、第三方或公开调用的契约。
- 修改公共请求、响应、事件或兼容口径。
- 存在复杂状态、嵌套载荷、幂等、安全、异步副作用或多类失败处理。

简单内部 HTTP/RPC、MQ 或 Job 契约直接在主方案写清，不创建独立文档。需要明细时按 `references/contract-detail-checklist.md` 填写，并保持 Dxx/Cxx 与主方案一致。

### 7. 校验并进入任务拆分

完成后将设计状态改为“已完成”，清除模板占位和阻塞口径：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" sync-meta --feature-dir <需求目录>
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" validate --feature-dir <需求目录>
```

进入任务拆分前必须满足：

- 所有设计输入已闭环，关键 Dxx 均有有效 Cxx。
- 核心改动有真实代码落点。
- 必要契约明细已闭环；未触发时没有空目录或占位文档。
- 新版 SQL Gate 已确认且当前指纹有效；历史需求存在 `04-schema.sql` 时仍按 legacy 指纹校验。
- SQL Gate 仍与当前 `01-research.md`、`sql-draft.sql` 和确认指纹一致。
- 没有未解决的阻塞问题或残留模板内容。

需要用户授权的业务取舍、成本、公共契约或高风险变更，必须展示方案并获得明确确认。低风险、事实已闭合且用户已经授权连续推进时，给出精简方案摘要后可直接进入任务拆分，不再额外索要一次形式化确认。随后由 `$ggg-task-breakdown` 执行：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-tasks --feature-dir <需求目录> --design-confirmed
```

## 用户纠正

- 只影响方案且不改变 SQL 语义：更新 `02-design.md` 或接口明细。改变 SQL 语义时先更新 `sql-draft.sql` 并重走 SQL Gate；历史需求按需更新 `04-schema.sql`。
- 影响代码事实：回写 `01-research.md` 后重审相关 Dxx。
- 影响业务范围、规则、实例身份或验收标准：执行 `sync-clarification --impact baseline research design`，重新确认上游后继续。

不要绕过上游权威文档直接改变实现范围。

## 硬约束

- 未完成需求对齐或仍有阻塞问题时，不写正式方案。
- §0 不复制输入摘要；最小方案和复杂备选只在 Dxx 维护一次。
- 技术事实由 AI 查代码、配置、接口、SQL 或运行证据，不把技术判断转问用户。
- 普通工程取舍由 AI 推荐；只有业务、成本、兼容或发布风险需要用户授权。
- 不为未来可能、排查方便或抽象美观增加持久化、中间件、服务或字段。
- 无持久实例、简单内部契约或单服务链路只写一次具体原因，不展开完整身份字段、非 MySQL 明细、接口明细或时序图。
- SQL Gate 未确认或已失效时不得开始或完成技术方案。
- 本阶段不生成 `03-tasks.md`，不写业务代码。

## 完成标准

- `02-design.md` 能说明目标、身份或无持久实例、调用契约、数据承载、核心改动、调用链、风险和验证。
- 关键设计以 Dxx 为唯一决策真相，并保持 `Cxx → Dxx → Txx` 可追溯。
- 真实代码落点、事务/幂等/异常边界与兼容要求足以直接拆任务。
- SQL 和接口明细只在触发条件成立时展开，且内容与主方案一致。
- validate 通过；存在 schema 时确认有效；可以进入任务拆分。
