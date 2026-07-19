from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
WORKFLOW_ROOT = TEST_DIR.parent
SKILLS_ROOT = WORKFLOW_ROOT.parent
SCRIPTS_DIR = WORKFLOW_ROOT / "scripts"
ASSET_ROOT = WORKFLOW_ROOT / "assets" / "workflow"
REVIEW_LEDGER_HEADING = (
    "## 3. 问题账本（含历史）"
    if "## 3. 问题账本（含历史）"
    in (ASSET_ROOT / "templates" / "code-review-index-template.md").read_text(encoding="utf-8")
    else "## 3. 未关闭问题"
)
TEST_LEDGER_HEADING = (
    "## 3. 缺口账本（含历史）"
    if "## 3. 缺口账本（含历史）"
    in (ASSET_ROOT / "templates" / "test-report-index-template.md").read_text(encoding="utf-8")
    else "## 3. 未关闭缺口"
)


def skill_path(name: str, *parts: str) -> Path:
    staged = SKILLS_ROOT / name
    root = staged if staged.exists() else Path.home() / ".codex" / "skills" / name
    return root.joinpath(*parts)


sys.path.insert(0, str(SCRIPTS_DIR))

from workflow_contracts import (
    BASELINE_REQUIRED_TOKENS,
    CODE_REVIEW_INDEX_REQUIRED_TOKENS,
    CODE_REVIEW_ROUND_REQUIRED_TOKENS,
    DESIGN_REQUIRED_TOKENS,
    DESIGN_V4_REQUIRED_TOKENS,
    DESIGN_V5_REQUIRED_TOKENS,
    IMPLEMENTATION_LOG_REQUIRED_TOKENS,
    INTERFACE_DETAIL_REQUIRED_TOKENS,
    INTERFACE_DETAIL_V3_REQUIRED_TOKENS,
    QUICK_RECORD_REQUIRED_TOKENS,
    RESEARCH_REQUIRED_TOKENS,
    RESEARCH_V2_REQUIRED_TOKENS,
    TEST_REPORT_INDEX_REQUIRED_TOKENS,
    TEST_REPORT_ROUND_REQUIRED_TOKENS,
    TASK_V2_REQUIRED_TOKENS,
)
from workflow_validation import (
    extract_quality_paths,
    extract_sql_v3_ddl_entries,
    extract_section,
    implementation_task_ids,
    is_test_artifact,
    unresolved_research_questions,
    validate_baseline_doc,
    validate_code_review_completion,
    validate_design_doc,
    validate_design_precheck,
    validate_feature_dir,
    validate_implementation_completion,
    validate_implementation_precheck,
    validate_interface_details_dir,
    validate_quick_implementation_completion,
    validate_quick_boundary_ready,
    validate_quick_review_evidence,
    validate_quick_test_evidence,
    validate_research_doc,
    validate_schema_doc,
    validate_tasks_doc,
    validate_test_report_completion,
    validate_test_report_nonpass,
)
from implementation_session import (
    changed_paths,
    compare_recorded_paths,
    current_round_paths,
    current_snapshot,
    initial_dirty_snapshot,
    is_quality_file,
    next_round_number,
    quick_boundary_fingerprint,
    review_artifact_fingerprint,
    review_input_fingerprint,
    resolve_adopted_existing_files,
    test_artifact_fingerprint,
)
from sync_clarification_impact import ensure_defaults, reopen_baseline_confirmation, reset_from_baseline


def build_confirmed_baseline() -> str:
    template = (ASSET_ROOT / "templates" / "baseline-template.md").read_text(encoding="utf-8")
    return (
        template.replace("- 主项目：", "- 主项目：demo")
        .replace("- 主项目判断依据：", "- 主项目判断依据：用户指定 demo 为主项目")
        .replace(
            "| S1 | PRD / 用户消息 / 会议结论 / 原型 / 截图 / 代码证据 |  |  | 形成基线 / 形成疑问 / 明确不适用 |  |",
            "| S1 | 用户消息 | 用户消息:2026-07-13 | 生成一套试卷及答案 | 形成基线 | §2-§8、Q1 |",
        )
        .replace("- 一句话目标：", "- 一句话目标：生成试卷及答案（来源：S1）")
        .replace("- 核心流程：", "- 核心流程：用户发起后系统生成同批试卷和答案（来源：S1）")
        .replace("- 输入对象：", "- 输入对象：生成请求（来源：S1）")
        .replace("- 输出对象：", "- 输出对象：试卷和答案（来源：S1）")
        .replace("- 使用角色：", "- 使用角色：教师（来源：S1）")
        .replace("- 本期包含：", "- 本期包含：生成试卷和答案（来源：S1）")
        .replace("- 本期不做：", "- 本期不做：在线作答（来源：S1）")
        .replace("- 不做原因：", "- 不做原因：本期只交付 PDF（来源：S1）")
        .replace(
            "| B1 |  |  |  |  |  |  |  |  |  |  |  |  |",
            "| B1 | 生成 | 教师 | 课程页 | 发起生成 | 提交请求 | 生成内容 | 形成试卷和答案 | 生成批次 | 可下载 | 同批题目一致 | 失败重试复用批次 | S1 |",
        )
        .replace(
            "| B2 |  |  |  |  |  |  |",
            "| B2 | 同批试卷和答案题目一致 | 生成请求 | 两个 PDF | 不允许漂移 | 失败可重试 | S1 |",
        )
        .replace(
            "| B3 |  |  |  |  |  |  | 是 / 否 | 是 / 否 |  |  |",
            "| B3 | 生成批次 | batchId | 关联试卷和答案 | 请求幂等键 | batchId | 重试复用 | 是 | 否 | 后端生成 | S1 |",
        )
        .replace(
            "| B4 |  |  | 可直接复用 / 可扩展复用 / 只可参考 / 禁止复用 / 必须新增 |  |  | 是 / 否 |  |",
            "| B4 | 旧生成链路 | 单 PDF 生成 | 只可参考 | 新批次隔离 | 题目漂移 | 是 | S1 |",
        )
        .replace(
            "| B5 |  |  |  |  |  |",
            "| B5 | 同批一致性 | 对比两个 PDF 题目 | 固定候选数据 | 题目一致 | S1 |",
        )
        .replace("- 基线状态：澄清中 / 已确认", "- 基线状态：已确认")
        .replace(
            "- 最终反向确认：待确认 / 已确认（记录用户消息或确认时间）",
            "- 最终反向确认：已确认（用户消息 2026-07-13）",
        )
        .replace(
            "| Q1 |  | 用户意图 / 代码事实 / 设计选择 | Sxx（PRD 章节 / 用户消息 / 会议结论 / 原型 / 代码证据） |  |  | 用户 / 需求对齐 / 技术方案 |  | 待确认 / 已确认 / 转下游 |",
            "| Q1 | 是否保留历史版本 | 用户意图 | S1 | 口径存在歧义 | 数据身份 | 用户 | 保留历史版本 | 已确认 |",
        )
    )


def build_research_doc(evidence_location: str, claim_evidence_id: str = "E1") -> str:
    return f"""# 代码调研

<!-- GGG_RESEARCH_SCHEMA_VERSION: 2 -->

## 1. Baseline 验证清单

| baseline ID | baseline 条目 | 需要验证的代码位置 | 验证状态 | 代码事实 | 证据ID | 结论 | 结论ID | 风险 |
|---|---|---|---|---|---|---|---|---|
| B1 | 用户路径 | ReportController | 已验证 | 入口存在 | E1 | 可进入主链路 | C1 | 无 |
| B2 | 业务规则 | ReportService | 已验证 | 规则由服务保证 | E1 | 规则已闭合 | C1 | 无 |
| B3 | 数据身份 | report_record | 已验证 | reportId 隔离 | E1 | 数据身份已闭合 | C1 | 无 |
| B4 | 旧链路 | ReportService | 已验证 | 调用方已核对 | E1 | 可扩展复用 | C1 | 无 |
| B5 | 验收标准 | ReportController | 已验证 | 入口可验证 | E1 | 验收链路已闭合 | C1 | 无 |

## 2. 主链路代码事实

- 入口：ReportController.submit
- 核心处理与异步链路：ReportService.submit，同步处理
- 关联产物不变量及数据承载：reportId 对应 report_record
- 失败重试 / 主动再次操作：按 reportId 幂等复用
- 框架隐式链路（AOP / Filter / Interceptor / 动态 Bean / 事务 / 异常 / 生成代码）：已核对相关事务和异常处理
- 关键依赖和数据落点：demo-service 的 report_record

## 3. 旧链路副作用清单

| 旧能力 | 代码位置 | 现有语义 | 反向影响范围 | 与本需求关系 | 结论 | 结论ID | 说明 |
|---|---|---|---|---|---|---|---|
| 报告提交 | ReportService | 写入报告记录 | 提交接口 | 主链路 | 可扩展复用 | C1 | 需补状态隔离 |

## 4. 数据身份和状态维度对照

| 业务对象 | 唯一标识 | 去重维度 | 状态隔离维度 | 现有代码/表字段 | 是否满足 | 结论ID | 风险 |
|---|---|---|---|---|---|---|---|
| 报告 | reportId | reportId | userId + reportId | report_record.report_id | 是 | C1 | 低 |

## 5. 复用性分级

| 能力/代码 | 代码位置 | 复用等级 | 原因 | 需要改造点 | 结论ID |
|---|---|---|---|---|---|
| ReportService | ReportService | 可扩展复用 | 入口一致 | 补隔离字段 | C1 |

## 6. 旧能力反向影响检查

| 准备复用/改造的旧能力 | 调用方/影响面 | CodeGraph 证据 | 影响旧场景 | 结论 | 结论ID |
|---|---|---|---|---|---|
| ReportService.submit | ReportController | E1 | 无新增影响 | 可扩展复用 | C1 |

### 6.1 共享状态、枚举和类型语义影响矩阵

- 影响面判断：不涉及：测试样例不新增或修改共享状态、枚举、类型码或字段语义
- 检索范围：不涉及

| 共享语义 | 权威载体/存储值 | 消费场景 | 读取/传播位置 | 当前处理规则 | 新语义预期 | 代码改动结论 | 证据ID | 结论ID | 验证缺口 |
|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |  |

## 7. 跨项目依赖能力

| 项目 | Facade / HTTP / MQ / 表 | 当前能力 | 是否满足本需求 | 缺口 | 结论ID |
|---|---|---|---|---|---|
| demo-service | report_record | 支持写入 | 是 | 无 | C1 |

## 8. 结论账本（Claim Ledger）

| 结论ID | 关键结论 | 结论类型 | 证据ID | 证据等级 | 置信度 | 未覆盖范围 | 运行时证据缺口 | 若结论错误的影响 | 后续确认方式 |
|---|---|---|---|---|---|---|---|---|---|
| C1 | ReportService 可扩展复用 | 复用边界 | {claim_evidence_id} | 代码已证实 | 高 | 无 | 无 | 影响旧链路 | 无 |

## 9. 进入技术方案前疑问账本

| 编号 | 疑问 | 问题类型 | 准确来源 | 为什么不确定 | 影响范围 | 应由谁确认 | 确认结论/转交说明 | 结论ID | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| Q1 | 主链路是否闭合 | 代码事实 | E1 | 已查证 | 主链路 | 需求对齐 | E1 已证实主链路闭合 | C1 | 已确认 |

## 10. 残余风险和后续确认方式

- 已确认：主链路已覆盖。
- 未覆盖：无。
- 非阻塞风险：无。
- 阻塞风险：无

## 11. 代码证据索引

| 编号 | 项目 | 类型 | 位置 | 结论说明 |
|---|---|---|---|---|
| E1 | demo-service | Controller | {evidence_location} | 主入口 |
"""


def build_design_doc(source_claim: str = "C1") -> str:
    return f"""# 技术方案

<!-- GGG_DESIGN_SCHEMA_VERSION: 3 -->

- 设计状态：已完成
- MySQL 结构变更：无

## 〇、设计输入覆盖清单

| 输入ID | 输入类型 | 核心内容摘要 | 处理方式 | 对应Dxx/章节 | 不进入设计原因 |
|---|---|---|---|---|---|
| {source_claim} | 已闭合结论 | ReportService 可扩展复用 | 进入设计 | D1 / §2-§16 | 无 |

## 一、背景与目标

- 目标：提交报告。

## 二、实例身份与状态隔离

| 业务对象/记录 | 唯一标识 | 状态隔离维度 | 去重维度 | 生命周期 | 来源Cxx | 是否已确认 |
|---|---|---|---|---|---|---|
| 报告 | reportId | userId + reportId | reportId | 创建到完成 | {source_claim} | 是 |

### 2.2 后端自动推导与前端禁止传

| 字段/身份 | 后端获取方式 | 前端是否允许传 | 禁止原因 | 兜底/校验方式 | 来源Cxx |
|---|---|---|---|---|---|
| userId | 登录态 | 否 | 防止越权 | 校验登录用户 | {source_claim} |

## 三、前后端接口协作流

| 页面/动作 | 调用接口 | 首屏/点击后 | 请求关键字段 | 后端自动推导 | 前端禁止传 | 返回粒度 | 来源Cxx | 说明 |
|---|---|---|---|---|---|---|---|---|
| 提交 | submit | 提交后 | reportId | userId | userId | 结果 | {source_claim} | 提交报告 |

## 四、数据承载设计

| 数据/状态 | 承载方式 | MySQL | Redis | ES | MQ | 配置/缓存 | 选择原因 | 一致性/过期策略 | 来源Cxx |
|---|---|---|---|---|---|---|---|---|---|
| 报告记录 | MySQL | 是 | 否 | 否 | 否 | 否 | 长期业务事实 | 事务提交 | {source_claim} |

### 4.1 非 MySQL 承载明细

| 类型 | 标识（Key / Index / Topic / 配置项） | 数据结构/消息体 | 生命周期 | 一致性/过期策略 | 幂等/失败处理 | 来源Cxx | 来源Dxx |
|---|---|---|---|---|---|---|---|
| 不涉及：仅使用 MySQL 持久化 | - | - | - | - | - | - | - |

### 4.2 最小方案与复杂度准入

| 设计点 | 当前能力/可复用落点 | 最小可行方案 | 更复杂备选 | 不采用复杂方案原因 | 触发升级条件 | 来源Cxx | 对应Dxx |
|---|---|---|---|---|---|---|---|
| 报告提交 | 现有 ReportService 已承载提交主链路 | 扩展现有 Service 并复用事务边界 | 新建独立服务和异步队列 | 当前单体事务可满足一致性且新增组件只会增加维护成本 | 出现跨系统异步处理且同步耗时超过已确认目标时再升级 | {source_claim} | D1 |

## 五、SQL 表设计

### 5.1 SQL 字段风格参考

| 参考项目/模块 | 参考表 | 公共字段风格 | 逻辑删除字段 | 时间字段 | 用户字段口径 | 索引命名风格 | 说明 |
|---|---|---|---|---|---|---|---|
| demo | report_record | id/create_time | is_delete | create_time | create_user | idx_xxx | {source_claim} |

### 5.2 `user_id` 设计判断

| 是否需要 `user_id` | 用户语义 | 身份来源 | 是否前端可传 | 是否后端推导 | 是否参与唯一键/索引 | 与实例身份关系 | 说明 |
|---|---|---|---|---|---|---|---|
| 是 | 学生 | 登录态 | 否 | 是 | 是 | 隔离维度 | {source_claim} |

### 5.3 SQL 最小化与准入检查

#### 表准入

| 表 | 变更类型 | 承载业务事实 | 现有承载评估 | 写入事件 | 核心查询 | 生命周期 | 最小方案 | 不采用更小方案原因 | 来源Cxx | 设计ID |
|---|---|---|---|---|---|---|---|---|---|---|
| report_record | 修改 | 报告提交记录 | 现有表已承载报告事实，只需补齐报告标识约束 | 提交报告时写入 | 按 report_id 查询单条报告 | 长期 | 修改现有表而不新建表 | 不改库无法稳定保存业务唯一标识 | {source_claim} | D1 |

#### 字段准入

| 表 | 字段 | 字段性质 | 来源/生成规则 | 写入时机 | 读取/约束场景 | 是否可推导 | 冗余一致性风险 | 不落库后果 | 来源Cxx | 设计ID |
|---|---|---|---|---|---|---|---|---|---|---|
| report_record | report_id | 业务事实 | 由已创建报告的真实 ID 写入 | 提交报告时 | 查询报告并保证业务唯一 | 否 | 非冗余字段，不存在双写一致性 | 无法稳定定位和约束报告 | {source_claim} | D1 |

#### 索引与约束准入

| 表 | 索引/约束 | 对应查询或约束 | 字段顺序依据 | 现有索引复用/重复检查 | 预期收益 | 写入/空间成本 | 验证方式 | 来源Cxx | 设计ID |
|---|---|---|---|---|---|---|---|---|---|
| report_record | uk_report_id(report_id) | report_id 业务唯一并按该字段等值查询 | 单字段等值查询，无组合顺序 | 现有索引未覆盖 report_id 且无重复列组合 | 唯一约束并避免全表扫描 | 每次写入增加一次唯一索引维护 | SHOW INDEX 并执行重复写入与查询验证 | {source_claim} | D1 |

#### 线上变更与兼容

| 变更对象 | 现有数据/规模 | DDL/锁风险 | 历史数据处理 | 读写兼容顺序 | 回滚边界 | 验证方式 |
|---|---|---|---|---|---|---|
| report_record.report_id | 测试场景按小表验证，生产规模需执行前查询 | 修改旧表可能锁表，按实际 MySQL 版本确认在线 DDL | 发布前检查空值和重复值并按业务来源回填 | 先加兼容字段与索引，再发布写入和读取代码 | 回滚代码前保留字段，确认无新写入后再回滚 DDL | 执行前统计、SHOW CREATE TABLE、回填校验和查询验证 |

### 5.4 表结构概览

| 设计ID | 表名 | 定位 | 新增/修改 | 关键字段 | 主键/唯一键 | 索引 | 来源Cxx | 说明 |
|---|---|---|---|---|---|---|---|---|
| D1 | report_record | 主表 | 修改 | report_id | id | idx_report_id | {source_claim} | 复用 |

### 5.5 字段设计（新增表或关键改表时）

| 设计ID | 表 | 字段 | 类型 | 必填 | 默认值 | 含义 | 来源Cxx | 备注 |
|---|---|---|---|---|---|---|---|---|
| D1 | report_record | report_id | bigint | 是 | 0 | 报告 | {source_claim} | 复用 |

### 5.6 ER 图（仅新增表时）

```plantuml
@startuml
entity "report_record" as report_record {{
  * id : bigint
}}
@enduml
```

## 六、核心改动

### 6.1 改动清单

| 设计ID | 项目 | 类型 | 类/文件/表 | 改动类型 | 来源Cxx | 改动说明 |
|---|---|---|---|---|---|---|
| D1 | demo | Service | ReportService | 修改 | {source_claim} | 提交 |

### 6.2 旧逻辑与新逻辑差异

| 维度 | 旧逻辑 | 新逻辑 | 改动原因 |
|---|---|---|---|
| 提交 | 旧 | 新 | {source_claim} |

## 七、主链路与依赖

### 7.1 核心调用链

| 调用方 | 被调方 | 接口/方法 | 用途 | 说明 |
|---|---|---|---|---|
| Controller | Service | submit | 提交 | {source_claim} |

### 7.2 事务与异常处理

- 事务边界：Service。
- 幂等策略：reportId。
- 关键异常处理：业务异常。

### 7.3 主时序图

```plantuml
@startuml
actor User
User -> Backend: submit
@enduml
```

## 八、接口设计

### 接口总表

| 设计ID | 接口名称 | 新增/修改 | 请求方式 | 路径/方法 | 所属项目 | 首屏/点击后/提交后 | 后端自动推导 | 前端禁止传 | 接口文档地址 | 来源Cxx | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D1 | 提交 | 修改 | POST | /submit | demo | 提交后 | userId | userId | interface-details/02-interface-01-submit.md | {source_claim} | 复用 |

## 九、枚举、状态与常量

| 名称 | 所属项目/类 | 类型 | 取值 | 用途 | 新增/修改 |
|---|---|---|---|---|---|
| Status | demo | Enum | 1 | 状态 | 复用 |

## 十三、设计决策记录

| 设计ID | 决策点 | 当前事实/约束 | 最小可行选择 | 更复杂备选 | 不采用复杂方案原因 | 来源Cxx | 影响/代价 | 触发升级条件 | 验证方式 |
|---|---|---|---|---|---|---|---|---|---|
| D1 | 提交链路 | ReportService 已承载提交且事务边界清晰 | 复用 ReportService 并修改旧表 | 新增 Service、独立表和 MQ | 当前链路可满足同步提交，引入额外组件会增加一致性成本 | {source_claim} | 修改范围小，但需验证旧表兼容 | 跨系统异步处理成为已确认要求时升级 | 编译、接口测试和数据唯一性验证 |

## 十六、测试链路与风险

### 测试链路

| 场景 | 关注点 | 验证方式 | 说明 |
|---|---|---|---|
| 主流程 | 提交 | 接口 | {source_claim} |

### 关键风险

| 风险点 | 影响 | 规避动作 | 是否阻塞任务拆分 |
|---|---|---|---|
| 配置 | 中 | 确认 | 否 |
"""


def build_design_doc_v4(
    source_claim: str = "C1",
    *,
    mysql_change: bool = False,
    state: str = "已完成",
    detail_value: str = "无需：简单内部方法，无独立契约明细",
    include_non_mysql_detail: bool = True,
) -> str:
    sql_section = (
        f"""- 精确结构：见 `04-schema.sql`

| 设计ID | 变更对象 | 承载事实/变更理由 | 现有结构复用结论 | 核心写入/查询 | 索引/约束依据 | 兼容/回滚/验证 | 来源Cxx |
|---|---|---|---|---|---|---|---|
| D1 | report_record.report_id | 持久化报告业务唯一标识 | 现有表可复用，仅补字段和唯一约束 | 提交时写入；按 report_id 查询 | 业务唯一且等值查询 | 先兼容读写；保留字段回滚；执行重复写入验证 | {source_claim} |"""
        if mysql_change
        else f"- 无 MySQL 结构变更：复用现有表和字段即可（{source_claim}）"
    )
    non_mysql_detail = (
        """| 类型 | 标识（Key / Index / Topic / 配置项） | 数据结构/消息体 | 生命周期 | 一致性/过期策略 | 幂等/失败处理 | 来源Cxx | 来源Dxx |
|---|---|---|---|---|---|---|---|
| 不涉及：不使用非 MySQL 载体 |  |  |  |  |  |  |  |"""
        if include_non_mysql_detail
        else ""
    )
    return f"""# 技术方案

<!-- GGG_DESIGN_SCHEMA_VERSION: 4 -->

- 设计状态：{state}
- MySQL 结构变更：{'有' if mysql_change else '无'}

## 〇、设计输入去向

| 输入ID | 处理方式 | 对应Dxx/章节或原因 |
|---|---|---|
| {source_claim} | 进入设计 | D1 |

## 一、背景与目标

- 一句话目标：复用 ReportService 提交报告。
- 本期包含：内部提交行为。
- 本期不做：新增异步链路。
- 关键约束：保持旧调用兼容。

## 二、实例身份与可信边界

| 业务对象/记录 | 唯一标识 | 状态隔离维度 | 去重维度 | 生命周期 | 来源Cxx | 是否已确认 |
|---|---|---|---|---|---|---|
| 不涉及：本轮不新增持久业务实例 |  |  |  |  |  |  |

| 字段/身份 | 后端获取方式 | 外部是否允许传 | 可信边界/禁止原因 | 兜底/校验方式 | 来源Cxx |
|---|---|---|---|---|---|
| 不涉及：内部调用不接收外部身份 |  |  |  |  |  |

## 三、调用方与接口契约

| 设计ID | 调用方/触发事件 | 接口/消息/任务 | 类型 | 输入关键字段 | 后端推导/可信边界 | 输出结果 | 独立明细 | 来源Cxx | 说明 |
|---|---|---|---|---|---|---|---|---|---|
| D1 | ReportController 提交请求 | ReportService.submit | 内部方法 | reportId | userId 来自登录态且不接收外部覆盖 | 返回既有或新建报告 | {detail_value} | {source_claim} | 保持旧响应 |

## 四、数据承载设计

| 数据/状态 | 承载方式 | MySQL | Redis | ES | MQ | 配置/缓存 | 选择原因 | 一致性/过期策略 | 来源Cxx |
|---|---|---|---|---|---|---|---|---|---|
| 不涉及：本轮不新增数据载体 |  |  |  |  |  |  |  |  |  |

{non_mysql_detail}

## 五、SQL 变更说明

{sql_section}

## 六、核心改动

| 设计ID | 项目 | 类型 | 类/文件/表 | 改动类型 | 来源Cxx | 改动说明 |
|---|---|---|---|---|---|---|
| D1 | demo | Service | ReportService.submit | 修改 | {source_claim} | 按 reportId 幂等提交并保持旧返回 |

| 维度 | 旧逻辑 | 新逻辑 | 改动原因 |
|---|---|---|---|
| 重复提交 | 重复创建 | 返回既有记录 | 满足幂等约束 |

## 七、主链路与依赖

| 调用方 | 被调方 | 接口/方法/事件 | 用途 | 说明 |
|---|---|---|---|---|
| ReportController | ReportService | submit | 提交报告 | 单服务同步链路 |

- 事务边界：ReportService 单事务。
- 幂等策略：按 reportId 查询后写入。
- 关键异常处理：业务异常沿现有异常处理器返回。
- 时序图：不需要
- 不需要原因：单服务同步调用且没有复杂事务分支。

## 十三、设计决策记录

| 设计ID | 决策点 | 当前事实/约束 | 最小可行选择 | 更复杂备选 | 不采用复杂方案原因 | 来源Cxx | 影响/代价 | 触发升级条件 | 验证方式 |
|---|---|---|---|---|---|---|---|---|---|
| D1 | 报告提交幂等 | ReportService 已承载提交主链路 | 在现有 Service 内按 reportId 幂等处理 | 新增异步队列和独立服务 | 当前同步链路足以满足目标，复杂方案会增加一致性成本 | {source_claim} | 仅修改现有主链路 | 出现已确认的跨系统异步处理要求 | 单元测试覆盖首次和重复提交 |

## 十六、测试链路与风险

| 场景 | 关注点 | 最小验证方式 | 说明 |
|---|---|---|---|
| 首次和重复提交 | 幂等结果 | ReportService 单元测试 | 验证同一 reportId |

| 风险点 | 影响 | 规避动作 | 是否阻塞任务拆分 |
|---|---|---|---|
| 旧调用兼容 | 返回变化会影响调用方 | 保持响应结构并回归旧调用 | 否 |
"""


def build_interface_detail(design_id: str = "D1", source_claim: str = "C1") -> str:
    return f"""# 提交接口

<!-- GGG_INTERFACE_SCHEMA_VERSION: 2 -->

## 1. 基本信息

| 项 | 内容 |
|---|---|
| 设计ID | {design_id} |
| 来源Cxx | {source_claim} |
| 接口名称 | 提交 |
| 新增 / 修改 | 修改 |
| 所属项目 | demo |
| 接口类型 | HTTP |
| 请求方式 | POST |
| 接口路径 / 方法 | /submit |
| 调用方 | 管理端 |
| 处理入口 | ReportController.submit |
| 关联表 / 关键对象 | report_record |
| 关键依赖 | ReportService |
| 说明 | 提交报告 |

## 2. 契约与参数

### 2.1 请求参数表

| 字段 | 位置 | 类型 | 必填 | 示例值 | 来源 | 是否后端推导 | 前端是否允许传 | 说明 |
|---|---|---|---|---|---|---|---|---|
| reportId | Body | long | 是 | 1001 | 前端 | 否 | 是 | 报告ID |
| userId | Context | long | 是 | 2001 | 登录态 | 是 | 否 | 当前用户 |

### 2.2 响应参数表

| 字段 | 类型 | 说明 |
|---|---|---|
| code | int | 业务状态码 |
| msg | string | 提示信息 |
| data | object | 提交结果 |
| data.reportId | long | 报告ID |

### 2.3 请求 JSON 示例

```json
{{"reportId": 1001}}
```

### 2.4 响应 JSON 示例

```json
{{"code": 200, "msg": "success", "data": {{"reportId": 1001}}}}
```

### 2.5 参数校验与兼容规则

- 参数校验：reportId 必须大于 0
- 后端自动推导字段：userId
- 前端禁止传字段：userId
- 关键业务规则：按 userId 校验报告归属
- 兼容旧参数 / 旧返回结构：保持现有响应外层结构

## 3. 处理链路

### 3.1 核心处理步骤

1. 校验 reportId 并从登录态获取 userId。
2. 校验报告归属后提交。

### 3.2 关键依赖与数据落点

| 类型 | 名称 | 用途 | 关键输入 / 输出 | 说明 |
|---|---|---|---|---|
| Service | ReportService | 提交报告 | reportId / 结果 | 主链路 |

### 3.3 接口流程图

```plantuml
@startuml
start
:校验并提交;
stop
@enduml
```

### 3.4 异常与失败处理

| 场景 | 错误码 / 返回 | 调用方感知 | 处理方式 |
|---|---|---|---|
| reportId 非法 | 400 | 参数错误 | 直接返回 |

## 4. 测试链路

| 链路 / 场景 | 关注点 | 验证方式 | 说明 |
|---|---|---|---|
| 主流程 | 提交成功 | 接口 | 校验返回与数据 |
"""


def build_schema_sql(source_claim: str = "C1", design_id: str = "D1") -> str:
    return f"""-- GGG_SQL_SCHEMA_VERSION: 2
-- 变更目标: 新增报告记录表
-- 来源Cxx: {source_claim}
-- 来源Dxx: {design_id}
-- SQL参考表: demo.old_report_record
-- SQL参考证据: demo/mapper/OldReportMapper.xml 中的表字段与索引定义
-- 最小变更结论: 只新增承载报告唯一事实的记录表，不增加缓存、快照或统计字段
-- 现有结构复用评估: 旧表生命周期不同且无法表达 report_id 唯一性，因此不复用
-- 核心写入: 提交报告时按 report_id 写入一次
-- 核心查询: 按 report_id 等值查询单条记录
-- 索引/约束依据: report_id 是业务唯一键且用于等值查询，使用唯一索引
-- 数据规模与DDL风险: 新建空表，无存量回填和旧表锁表风险
-- 执行前备份: 新表无需备份
-- 回滚方式: DROP TABLE report_record
-- 验证SQL: SHOW CREATE TABLE report_record

CREATE TABLE `report_record` (
  `id` bigint NOT NULL COMMENT '主键',
  `report_id` bigint NOT NULL COMMENT '报告ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_id` (`report_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报告记录';
"""


def build_design_doc_v5(
    source_claim: str = "C1",
    *,
    mysql_change: bool = False,
    state: str = "已完成",
    detail_value: str = "interface-details/02-interface-01-submit.md",
    caller: str = "管理端提交",
    contract_type: str = "HTTP",
    identifier: str = "POST /submit",
    input_fields: str = "reportId, userId",
    trusted_fields: str = "userId=登录态",
    forbidden_fields: str = "userId",
    output_fields: str = "code, msg, data, data.reportId",
    side_effects: str = "写入 report_record",
    ddl_object: str = "report_record",
    ddl_operation: str = "create",
    ddl_members: str = "id, report_id, PRIMARY KEY, uk_report_id",
    ddl_risk: str = "普通",
    ddl_risk_reason: str = "新建隔离空表，无存量数据和锁表风险",
) -> str:
    text = build_design_doc_v4(
        source_claim,
        mysql_change=mysql_change,
        state=state,
        detail_value=detail_value,
    ).replace(
        "<!-- GGG_DESIGN_SCHEMA_VERSION: 4 -->",
        "<!-- GGG_DESIGN_SCHEMA_VERSION: 5 -->",
    )
    old_contract = extract_section(text, "## 三、调用方与接口契约")
    new_contract = f"""## 三、调用方与接口契约

| 设计ID | 调用方/触发事件 | 契约类型 | 契约标识 | 输入关键字段 | 后端推导字段/来源 | 禁止外部传字段 | 输出字段 | 副作用 | 独立明细 | 来源Cxx | 说明 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D1 | {caller} | {contract_type} | {identifier} | {input_fields} | {trusted_fields} | {forbidden_fields} | {output_fields} | {side_effects} | {detail_value} | {source_claim} | 保持契约兼容 |"""
    text = text.replace(old_contract, new_contract, 1)

    if mysql_change:
        old_carrier = extract_section(text, "## 四、数据承载设计")
        new_carrier = f"""## 四、数据承载设计

| 数据/状态 | 承载方式 | MySQL | Redis | ES | MQ | 配置/缓存 | 选择原因 | 一致性/过期策略 | 来源Cxx |
|---|---|---|---|---|---|---|---|---|---|
| 报告唯一记录 | report_record 表 | 是 | 否 | 否 | 否 | 否 | 持久化 report_id 唯一事实 | 单事务写入并由唯一约束保证一致性 | {source_claim} |"""
        text = text.replace(old_carrier, new_carrier, 1)

    old_sql = extract_section(text, "## 五、SQL 变更说明")
    sql_body = (
        f"""- 精确结构：有 MySQL 结构变更时见 `04-schema.sql`

| 设计ID | 变更对象 | 操作 | DDL对象覆盖 | 风险等级 | 风险依据/执行条件 | 承载事实/变更理由 | 现有结构复用结论 | 核心写入/查询 | 索引/约束依据 | 兼容/回滚/验证 | 来源Cxx |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D1 | {ddl_object} | {ddl_operation} | {ddl_members} | {ddl_risk} | {ddl_risk_reason} | 持久化报告唯一事实 | 现有表语义不同，新建隔离对象 | 提交写入并按 report_id 查询 | report_id 业务唯一 | 先建表再发布；回滚删除新表；SHOW CREATE TABLE 验证 | {source_claim} |"""
        if mysql_change
        else f"- 无 MySQL 结构变更：复用现有表与字段即可（{source_claim}）"
    )
    text = text.replace(old_sql, f"## 五、SQL 变更说明\n\n{sql_body}", 1)
    return text


def build_interface_detail_v3(
    design_id: str = "D1",
    source_claim: str = "C1",
    *,
    caller: str = "管理端提交",
    contract_type: str = "HTTP",
    identifier: str = "POST /submit",
    side_effects: str = "写入 report_record",
    no_response: bool = False,
) -> str:
    response_table = (
        "| 不涉及：异步消费完成后无同步响应 | - | 结果通过后续事件体现 |"
        if no_response
        else """| code | int | 业务状态码 |
| msg | string | 提示信息 |
| data | object | 提交结果 |
| data.reportId | long | 报告ID |"""
    )
    response_json = "null" if no_response else '{"code": 200, "msg": "success", "data": {"reportId": 1001}}'
    return f"""# 提交契约

<!-- GGG_INTERFACE_SCHEMA_VERSION: 3 -->

## 1. 基本信息

| 项 | 内容 |
|---|---|
| 设计ID | {design_id} |
| 来源Cxx | {source_claim} |
| 契约名称 | 报告提交 |
| 新增 / 修改 | 修改 |
| 所属项目 | demo |
| 契约类型 | {contract_type} |
| 契约标识 | {identifier} |
| 调用方 / 触发事件 | {caller} |
| 处理入口 | ReportController.submit |
| 关联表 / 关键对象 | report_record |
| 关键依赖 | ReportService |
| 说明 | 提交报告 |

## 2. 契约与参数

### 2.1 请求参数表

| 字段 | 位置 | 类型 | 必填 | 示例值 | 来源 | 是否后端推导 | 外部是否允许传 | 说明 |
|---|---|---|---|---|---|---|---|---|
| reportId | {'Message' if contract_type == 'MQ' else 'Body'} | long | 是 | 1001 | 外部 | 否 | 是 | 报告ID |
| userId | Context | long | 是 | 2001 | 登录态 | 是 | 否 | 当前用户 |

### 2.2 响应参数表

| 字段 | 类型 | 说明 |
|---|---|---|
{response_table}

### 2.3 请求 JSON 示例

```json
{{"reportId": 1001}}
```

### 2.4 响应 JSON 示例

```json
{response_json}
```

### 2.5 参数校验与兼容规则

- 参数校验：reportId 必须大于 0
- 关键业务规则：按 userId 校验报告归属
- 兼容旧契约：保持现有字段语义
- 输出副作用：{side_effects}

## 3. 处理链路

### 3.1 核心处理步骤

1. 校验 reportId 并从登录态获取 userId。
2. 校验归属并提交报告。

### 3.2 关键依赖与数据落点

| 类型 | 名称 | 用途 | 关键输入 / 输出 | 说明 |
|---|---|---|---|---|
| Service | ReportService | 提交报告 | reportId / 结果 | 主链路 |

### 3.3 接口流程图

```plantuml
@startuml
start
:校验并提交;
stop
@enduml
```

### 3.4 异常与失败处理

| 场景 | 错误码 / 返回 | 调用方感知 | 处理方式 |
|---|---|---|---|
| reportId 非法 | 400 | 参数错误 | 直接拒绝 |

## 4. 测试链路

| 链路 / 场景 | 关注点 | 验证方式 | 说明 |
|---|---|---|---|
| 主流程 | 提交成功 | 接口 | 校验结果与副作用 |
"""


def build_schema_sql_v3(
    source_claim: str = "C1",
    design_id: str = "D1",
    *,
    risk_reason: str = "新建隔离空表，无存量数据和锁表风险",
    comment_with_semicolon: bool = False,
) -> str:
    field_comment = "主键;由数据库分配" if comment_with_semicolon else "主键"
    table_comment = "报告记录;按业务唯一" if comment_with_semicolon else "报告记录"
    marker = json.dumps(
        {
            "object": "report_record",
            "operation": "create",
            "members": ["id", "report_id", "PRIMARY KEY", "uk_report_id"],
            "risk": "普通",
            "risk_reason": risk_reason,
            "claims": [source_claim],
            "designs": [design_id],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""-- GGG_SQL_SCHEMA_VERSION: 3
-- 变更目标: 新增报告记录表
-- 来源Cxx: {source_claim}
-- 来源Dxx: {design_id}
-- SQL参考表: demo.old_report_record
-- SQL参考证据: demo/mapper/OldReportMapper.xml 的字段与索引定义
-- 最小变更结论: 仅新增承载报告唯一事实的隔离表
-- 现有结构复用评估: 旧表生命周期不同，无法承载 report_id 唯一性
-- 核心写入: 提交报告时按 report_id 写入一次
-- 核心查询: 按 report_id 等值查询单条记录
-- 索引/约束依据: report_id 是业务唯一键并用于等值查询
-- 数据规模与DDL风险: 新建空表，无存量回填和锁表风险
-- 执行前备份: 新表无需备份
-- 回滚方式: 删除本次新建表
-- 验证SQL: SHOW CREATE TABLE report_record

-- GGG_DDL_OBJECT: {marker}
CREATE TABLE `report_record` (
  `id` bigint NOT NULL COMMENT '{field_comment}',
  `report_id` bigint NOT NULL COMMENT '报告ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_id` (`report_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='{table_comment}';
"""


def build_high_risk_schema_sql_v3(
    source_claim: str = "C1",
    design_id: str = "D1",
    *,
    risk_reason: str = "修改非空列定义会重建存量表并持有元数据锁",
) -> str:
    marker = json.dumps(
        {
            "object": "report_record",
            "operation": "alter",
            "members": ["report_id"],
            "risk": "高风险",
            "risk_reason": risk_reason,
            "claims": [source_claim],
            "designs": [design_id],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""-- GGG_SQL_SCHEMA_VERSION: 3
-- 变更目标: 修改报告唯一标识类型
-- 来源Cxx: {source_claim}
-- 来源Dxx: {design_id}
-- SQL参考表: demo.report_record
-- SQL参考证据: demo/mapper/ReportMapper.xml 的 report_id 映射
-- 最小变更结论: 只修改 report_id 类型，不新增冗余字段
-- 现有结构复用评估: 继续复用 report_record
-- 核心写入: 提交时写入 report_id
-- 核心查询: 按 report_id 等值查询
-- 索引/约束依据: 保留既有唯一约束
-- 数据规模与DDL风险: 存量大表可能重建并持有元数据锁
-- 执行前备份: 备份 report_record
-- 回滚方式: 恢复原列定义
-- 验证SQL: SHOW CREATE TABLE report_record

-- GGG_DDL_OBJECT: {marker}
ALTER TABLE `report_record` MODIFY COLUMN `report_id` bigint NOT NULL;
"""


def build_design_precheck(source_claim: str = "C1") -> str:
    text = build_design_doc(source_claim).replace("- 设计状态：已完成", "- 设计状态：SQL待确认").replace(
        "- MySQL 结构变更：无", "- MySQL 结构变更：有"
    )
    for heading in [
        "## 五、SQL 表设计", "## 六、核心改动", "## 七、主链路与依赖", "## 八、接口设计",
        "## 九、枚举、状态与常量", "## 十、缓存设计（按需）", "## 十一、消息队列设计（按需）",
        "## 十二、配置变更", "## 十三、设计决策记录", "## 十四、影响范围",
        "## 十五、发布与灰度策略", "## 十六、测试链路与风险",
    ]:
        section = extract_section(text, heading)
        if section:
            text = text.replace(section, heading, 1)
    return text


def build_tasks_doc(source: str = "D1 / C1") -> str:
    return f"""# 任务拆分

## 1. 编码范围

- 主项目：demo
- 涉及项目：demo
- 本轮编码目标：实现报告提交能力
- 仓库改动类型：Java
- 不进入编码任务的事项：测试执行、发布操作

## 2. 拆分方式和执行顺序

- 拆分依据：按报告提交主链路拆分为一个编码任务。
- 推荐执行顺序：T1
- 跨项目或关键代码依赖：无

## 3. 编码任务

| 编号 | 开发任务 | 来源依据 | 所属项目 | 预计修改文件/符号 | 依赖任务 | 完成标准 |
|---|---|---|---|---|---|---|
| T1 | 实现报告提交服务 | {source} | demo | src/main/java/demo/ReportService.java | - | ReportService 按 reportId 保存报告且重复提交返回既有结果 |

## 4. 任务详情

### T1 实现报告提交服务

- 来源依据：{source}
- 所属项目：demo
- 依赖任务：-
- 预计修改文件/符号：src/main/java/demo/ReportService.java
- 主要实现内容：
  - 按 reportId 保存并返回报告记录。
  - interface-details/02-interface-01-submit.md 对应的入参和结果由该服务承载。
- 代码边界：
  - 不改变其他报告查询链路。
- 完成标准：
  - ReportService 按 reportId 保存报告且重复提交返回既有结果。

## 5. 完成定义

- 所有任务有来源依据。
- 所有任务有代码落点和完成标准。
- 不包含人工执行和发布任务。
"""


def build_tasks_doc_v2(source: str = "D1 / C1") -> str:
    return f"""<!-- GGG_TASK_SCHEMA_VERSION: 2 -->
# 任务拆分

## 1. 编码范围

- 主项目：demo
- 涉及项目：demo
- 本轮编码目标：实现报告幂等提交。
- 仓库改动类型：Java / 测试代码
- 不进入编码任务的事项：测试执行、测试报告和发布操作。

## 2. 拆分依据

- 纵向业务边界：提交入口、幂等服务逻辑和对应测试代码构成一个完整能力。
- 跨项目拆分依据：仅 demo 项目。
- 关键代码依赖：无跨任务依赖。
- 测试代码归属：并入对应功能 T1。

## 3. 任务总览

| 编号 | 开发任务 | 所属项目 | 依赖任务 |
|---|---|---|---|
| T1 | 实现报告幂等提交能力 | demo | - |

## 4. 任务详情

### T1 实现报告幂等提交能力

- 来源依据：{source}
- 预计修改文件/符号：src/main/java/demo/ReportService.java；src/test/java/demo/ReportServiceTest.java
- 主要实现内容：
  - 按 reportId 查询既有记录，不存在时在当前事务内创建。
  - 在 ReportServiceTest 中覆盖首次提交和重复提交。
- 代码边界：
  - 保持现有 Controller 请求和响应契约，不新增异步链路。
- 完成标准：
  - 代码结果与关键行为：首次提交创建记录，重复提交返回同一记录。
  - 必要测试代码：ReportServiceTest 覆盖首次提交和重复提交。
  - 最小验证：运行 ReportServiceTest 的首次和重复提交用例。

## 5. 完成定义

- 所有任务均产生仓库代码改动。
- D1 已由 T1 承接，项目和依赖关系明确。
- 必要测试代码并入功能任务，未生成测试执行或报告任务。
"""


def build_tasks_doc_v2_with_second_task() -> str:
    return (
        build_tasks_doc_v2()
        .replace(
            "| T1 | 实现报告幂等提交能力 | demo | - |",
            "| T1 | 实现报告幂等提交能力 | demo | - |\n"
            "| T2 | 实现报告查询能力 | demo | T1 |",
        )
        .replace(
            "## 5. 完成定义",
            """### T2 实现报告查询能力

- 来源依据：D1 / C1
- 预计修改文件/符号：src/main/java/demo/ReportQueryService.java；src/test/java/demo/ReportQueryServiceTest.java
- 主要实现内容：
  - 按 reportId 查询并返回既有报告。
  - 在 ReportQueryServiceTest 中覆盖存在和不存在两类结果。
- 代码边界：
  - 不修改报告提交和持久化逻辑。
- 完成标准：
  - 代码结果与关键行为：存在时返回报告，不存在时返回空结果。
  - 必要测试代码：ReportQueryServiceTest 覆盖存在和不存在两类结果。
  - 最小验证：运行 ReportQueryServiceTest 的存在和不存在用例。

## 5. 完成定义""",
        )
    )


def validate_tasks_doc_v2_text(text: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "03-tasks.md"
        path.write_text(text, encoding="utf-8")
        return validate_tasks_doc(
            path,
            valid_design_ids={"D1"},
            valid_claim_ids={"C1"},
            required_core_design_ids={"D1"},
        )


def build_completed_implementation_log() -> str:
    text = (ASSET_ROOT / "templates" / "implementation-log-template.md").read_text(encoding="utf-8")
    text = text.replace(
        "| I |  | T |  |  |  |  |",
        "| I1 | 2026-07-13 | T1 | ReportService 按 reportId 保存且重复提交返回既有结果；见 ReportController.java:24 | src/ReportController.java<br>src/ReportResponse.java | 编译通过 | 无 |",
    ).replace(
        "| I |  | 通过 / 失败 / 未验证 |  |  |",
        "| I1 | mvn test | 通过 | 相关单测通过 |  |",
    ).replace(
        "| I |  | 代码设计 / 契约 / SQL / 权限 / 事务 / 异常日志 / 性能 / 注释 / 格式测试 |  | 通过 / 未通过 |  |",
        "| I1 | T1 | 主链路、接口契约、权限、异常日志、注释和格式测试 | src/ReportController.java:10、24；mvn test 通过 | 通过 | 无 |",
    ).replace(
        "| I | 不涉及（写明本轮没有复杂逻辑的原因） / `文件:行号`＋注释解释的顺序、并发或失败边界 | 不涉及 / `SQL文件`＋参考表或统一兜底＋公共字段/例外＋生产方言与测试 schema 区分 |",
        "| I1 | src/ReportController.java:24，说明重复提交返回既有结果的幂等边界 | 不涉及，本轮没有 SQL/DDL 文件 |",
    )
    return text


def build_confirmed_quick_template() -> str:
    text = (ASSET_ROOT / "templates" / "quick-record-template.md").read_text(encoding="utf-8")
    return (
        text.replace(
            "- 推进模式：quick（自动路由并已告知 / 用户明确指定）",
            "- 推进模式：quick（自动路由并已告知）",
        )
        .replace("- 路由依据：", "- 路由依据：目标单一且兼容边界明确")
        .replace("- 澄清状态：澄清中 / 已确认", "- 澄清状态：已确认")
        .replace(
            "- 最终边界确认：待确认 / 已确认（记录用户消息或确认时间）",
            "- 最终边界确认：已确认（用户消息 2026-07-18）",
        )
        .replace("- 一句话目标：", "- 一句话目标：实现报告幂等提交")
        .replace("- 改什么：", "- 改什么：调整报告提交服务并保持重复提交幂等")
        .replace("- 不改什么：", "- 不改什么：不改变其他报告查询链路")
        .replace(
            "- 预计主项目 / 代码范围：",
            "- 预计主项目 / 代码范围：demo；ReportController、ReportService 及对应测试",
        )
        .replace(
            "- 代表性验收例：`前置/输入 -> 用户操作或触发 -> 系统处理 -> 用户可见结果`",
            "- 代表性验收例：已存在 reportId 请求 -> 用户再次提交 -> 服务复用既有记录 -> 返回同一报告结果",
        )
        .replace(
            "- 失败 / 重复触发补充：不涉及 / `失败、重试或再次操作时的预期`",
            "- 失败 / 重复触发补充：重复触发不新增记录，异常沿用现有错误口径",
        )
        .replace(
            "- 兼容性检查：`现有调用方=无影响/有影响/未知；历史数据=无影响/有影响/未知；重复请求或重试=无影响/有影响/未知`",
            "- 兼容性检查：现有调用方=无影响；历史数据=无影响；重复请求或重试=按既有记录返回",
        )
        .replace("- 最小验收信号：", "- 最小验收信号：首次创建且重复提交返回同一记录")
        .replace(
            "| Q1 |  | 高影响阻塞 / 低风险 | PRD 章节 / 用户消息 |  |  | 待确认 / 已确认 |",
            "| Q1 | 重复提交口径 | 低风险 | 用户消息 2026-07-18 | 需确认幂等结果 | 返回既有记录 | 已确认 |",
        )
    )


def build_completed_quick_record() -> str:
    text = build_confirmed_quick_template()
    text = text.replace(
        "- 修改文件：",
        "- 修改文件：src/ReportController.java、src/ReportResponse.java",
    ).replace(
        "- 完成标准证据：",
        "- 完成标准证据：接口返回满足 quick 验收信号；见 ReportController.java:24",
    ).replace(
        "| quick 边界 | 代码设计 / 契约 / SQL / 权限 / 事务 / 异常日志 / 性能 / 注释 / 格式测试 |  | 通过 / 未通过 |  |",
        "| quick 边界 | 主链路、接口契约、权限、异常日志、注释和格式测试 | src/ReportController.java:10、24；mvn test 通过 | 通过 | 无 |",
    ).replace(
        "- 关键逻辑注释证据：不涉及（写明本轮没有复杂逻辑的原因） / `本轮修改文件:行号`＋注释解释的顺序、并发或失败边界",
        "- 关键逻辑注释证据：src/ReportController.java:24，说明重复提交返回既有结果的幂等边界",
    ).replace(
        "- Review Gate A：未执行 / 通过 / 需修改 / 阻塞",
        "- Review Gate A：通过",
    ).replace(
        "- Review Gate B：未执行 / 通过 / 需修改 / 阻塞",
        "- Review Gate B：通过",
    ).replace(
        "- Review 未关闭阻塞/必须修问题：",
        "- Review 未关闭阻塞/必须修问题：无",
    ).replace(
        "- Review 剩余风险：",
        "- Review 剩余风险：无",
    ).replace(
        "| A | 目标、禁止项与行为 | 通过 / 有问题 / 阻塞 |  |",
        "| A | 目标、禁止项与行为 | 通过 | quick 边界与 src/ReportController.java:10-24 一致 |",
    ).replace(
        "| A | 契约、数据、权限、兼容与越界 | 通过 / 有问题 / 阻塞 |  |",
        "| A | 契约、数据、权限、兼容与越界 | 通过 | 独立核对接口边界与权限约束 |",
    ).replace(
        "| B | 正确性、安全、失败边界与副作用 | 通过 / 有问题 / 阻塞 |  |",
        "| B | 正确性、安全、失败边界与副作用 | 通过 | 独立检查幂等与异常边界 |",
    ).replace(
        "| B | 可维护性、触发风险与验证充分性 | 通过 / 有问题 / 阻塞 |  |",
        "| B | 可维护性、触发风险与验证充分性 | 通过 | 复核实现验证记录与真实 diff |",
    ).replace(
        "|  | 通过 / 有问题 / 阻塞 | 通过 / 有问题 / 阻塞 |  |",
        "| src/ReportController.java | 通过 | 通过 | src/ReportController.java:10-24 |"
        "\n| src/ReportResponse.java | 通过 | 通过 | src/ReportResponse.java:1-8 |",
    ).replace(
        "- 验证命令 / 方式：",
        "- 验证命令 / 方式：mvn test",
    ).replace(
        "- 验证结果：",
        "- 验证结果：通过",
    ).replace(
        "- 未验证项：",
        "- 未验证项：无",
    )
    return text


def fill_completed_implementation_precheck(path: Path, round_id: str = "I1") -> None:
    text = path.read_text(encoding="utf-8")
    replacements = {
        "范围与主链路": (
            "本轮按 T1 完成报告提交主链路：校验、按 reportId 保存并返回结果",
            "03-tasks.md T1；quick 使用 quick.md 最小验收信号",
        ),
        "代码落点与职责": (
            "ReportController 负责接口边界，ReportService 负责幂等保存",
            "src/ReportController.java、ReportService.submit",
        ),
        "数据、契约与失败边界": (
            "按 reportId 保证重复提交复用既有结果，异常沿用项目处理",
            "02-design.md D1；ReportService.submit",
        ),
        "性能、外部调用与恢复": (
            "单次请求至多一次查询和一次写入，不在循环中执行 DB 或 RPC",
            "ReportService.submit 主链路与 Mapper 调用",
        ),
        "抽象选择与方案偏差": (
            "复用现有 Service 直接实现，不新增设计模式且不偏离方案",
            "02-design.md D1；项目现有 Controller-Service 结构",
        ),
        "验证策略": (
            "运行最接近的单元测试和编译，失败时先修复再重跑",
            "pom.xml test 配置；ReportServiceTest",
        ),
    }
    for item, (conclusion, evidence) in replacements.items():
        for placeholder_round in ["I", round_id]:
            text = text.replace(
                f"| {placeholder_round} | {item} |  |  | 通过 / 阻塞 |",
                f"| {round_id} | {item} | {conclusion} | {evidence} | 通过 |",
                1,
            )
    path.write_text(text, encoding="utf-8")


def run_implementation_precheck(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "workflow_cli.py"),
            "implementation-precheck",
            "--record",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def run_implementation_verify(
    path: Path,
    repo: Path,
    *,
    command: list[str] | None = None,
    label: str = "unit-test",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "workflow_cli.py"),
            "implementation-verify",
            "--record",
            str(path),
            "--cwd",
            str(repo),
            "--label",
            label,
            "--",
            *(command or [sys.executable, "-c", "print('verified')"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def build_completed_review_index(
    *,
    round_id: str = "R1",
    implementation_round: str = "I1",
    input_fingerprint: str = "b" * 64,
    artifact_fingerprint: str = "c" * 64,
    issue_rows: str = "",
) -> str:
    number = int(round_id[1:])
    return f"""# Code Review 索引

## 1. Review 轮次索引

| 轮次 | 时间 | 对应实现轮次 | Gate A | Gate B | 结论 | 明细文档 | 未关闭问题 | Review 输入指纹 | Review 工件指纹 |
|---|---|---|---|---|---|---|---|---|---|
| {round_id} | 2026-07-13 | {implementation_round} | 通过 | 通过 | 通过 | review-rounds/review-r{number:02d}.md | 无 | {input_fingerprint} | {artifact_fingerprint} |

## 2. 当前结论

- 最新轮次：{round_id}
- 当前结论：通过
- 是否允许进入测试验证：是
- 需要回到实现阶段的问题：无
- 对应实现轮次：{implementation_round}
- 实现差异指纹：{'a' * 64}
- Review 输入指纹：{input_fingerprint}
- Review 工件指纹：{artifact_fingerprint}

{REVIEW_LEDGER_HEADING}

| 问题编号 | 首次轮次 | 最新复审轮次 | 级别 | Gate | 问题 | 当前状态 | 关闭依据 |
|---|---|---|---|---|---|---|---|
{issue_rows}
"""


def build_completed_review_round(
    *,
    paths: tuple[str, ...] = ("src/ReportController.java",),
    round_id: str = "R1",
    implementation_round: str = "I1",
    fingerprint: str = "a" * 64,
    input_fingerprint: str = "b" * 64,
    issue_rows: str = "",
    closure_rows: str = "",
) -> str:
    manifest = "\n".join(
        f"| {path} | 修改 | T1 / D1 | 提交行为及调用方 | "
        f"{'DDL/数据' if path.endswith('.sql') else '业务逻辑'} | "
        f"T1 与 {path} | {'SQL/DDL' if path.endswith('.sql') else '正确性'} | 通过 |"
        for path in paths
    )
    gate_a = "\n".join(
        f"| {item} | 通过 | T1、D1 与完整 diff 独立核对 | 无 |"
        for item in [
            "需求要求但未实现",
            "已实现但行为偏差",
            "超出确认范围",
            "契约、数据、权限和兼容性",
            "结论与验证证据真实性",
        ]
    )
    gate_b = "\n".join(
        f"| {item} | {'不涉及' if item in {'数据一致性', '兼容性'} else '通过'} | "
        f"{'本轮未触发该风险，已核对完整 diff' if item in {'数据一致性', '兼容性'} else '独立核对 src/ReportController.java:1-20'} | 无 |"
        for item in ["正确性", "安全与权限", "数据一致性", "失败边界", "兼容性", "验证充分性"]
    )
    return f"""# Code Review 轮次明细

## 1. 基本信息与输入快照

- 轮次：{round_id}
- 评审时间：2026-07-13
- 评审范围：当前实现快照全部差异
- 对应实现轮次：{implementation_round}
- 实现差异指纹：{fingerprint}
- Review 输入指纹：{input_fingerprint}
- Review 工件指纹：{'c' * 64}
- 权威输入及 digest：baseline/tasks/diff 均已核对

## 2. 完整 Diff 覆盖

- 实际 diff 文件数：{len(paths)}
- 已覆盖文件数：{len(paths)}
- 未覆盖文件：无

| Diff 路径 | 变更类型 | 需求/任务来源 | 行为与影响面 | 风险标签 | Gate A 证据 | Gate B 模块 | 结论/CRxx |
|---|---|---|---|---|---|---|---|
{manifest}

## 3. Gate A：Spec Compliance

- Gate A 结论：通过

| 检查面 | 结论 | 独立证据 | CRxx/说明 |
|---|---|---|---|
{gate_a}

## 4. Gate B：Risk-driven Code Quality

- 风险级别：normal
- Gate B 结论：通过

### 4.1 核心质量面

| 核心面 | 结论 | 独立证据 | CRxx/说明 |
|---|---|---|---|
{gate_b}

### 4.2 触发的风险模块

| 模块 | Diff 触发证据 | 结论 | 独立证据（文件行号/命令） | CRxx |
|---|---|---|---|---|
| 当前实现主链路 | {paths[0]} | 通过 | {paths[0]}:1；验证记录 V1 | 无 |

## 5. 问题清单

| 问题编号 | 级别 | Gate | 文件行号/全局依据 | 问题 | 风险 | 建议 | 状态 |
|---|---|---|---|---|---|---|---|
{issue_rows}

## 6. 历史问题继承与修复闭环

| 问题编号 | 来源轮次 | 上轮状态 | 本轮结果 | 对应实现轮次 | 关闭依据 |
|---|---|---|---|---|---|
{closure_rows}

## 7. 评审结论

- 结论：通过
- 是否可进入测试验证：是
- 主要原因：Gate A 与 Gate B 均通过且完整 diff 已覆盖
- 剩余风险：无
- 未覆盖验证：无
"""


TEST_EVIDENCE_SHA = "d" * 64


def write_test_evidence(feature_dir: Path, content: bytes = b"HTTP 200 code=0\n") -> str:
    path = feature_dir / "reports" / "evidence" / "e1.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def build_completed_test_index(
    *,
    round_id: str = "T1",
    implementation_round: str = "I1",
    review_round: str = "R1",
    gap_rows: str = "",
) -> str:
    number = int(round_id[1:])
    return f"""# 测试报告索引

## 1. 测试轮次索引

| 轮次 | 时间 | 模式 | 结论 | 对应实现/Review | 明细文档 | 关联接口报告 | 未关闭缺口 |
|---|---|---|---|---|---|---|---|
| {round_id} | 2026-07-17 | formal-gate | 通过 | {implementation_round} / {review_round} | test-rounds/test-r{number:02d}.md | 不涉及 | 无 |

## 2. 当前测试结论

- 最新轮次：{round_id}
- 当前模式：formal-gate
- 当前结论：通过
- 测试阶段是否完成：是
- 对应实现轮次与差异指纹：{implementation_round} / {'a' * 64}
- 对应 Review 轮次：{review_round}
- 需要回到实现或评审的问题：无
- 剩余风险：无

{TEST_LEDGER_HEADING}

| 缺口编号 | 首次轮次 | 最近轮次 | 缺口 | 主要归因 | 当前状态 | 关闭轮次/证据 | 后续处理与复验条件 |
|---|---|---|---|---|---|---|---|
{gap_rows}
"""


def build_completed_test_round(
    *,
    round_id: str = "T1",
    implementation_round: str = "I1",
    review_round: str = "R1",
    fingerprint: str = "a" * 64,
    baseline_ids: tuple[str, ...] = ("B1",),
    diff_paths: tuple[str, ...] = ("src/ReportController.java",),
    gap_rows: str = "",
    evidence_sha: str = TEST_EVIDENCE_SHA,
) -> str:
    basis_rows: list[str] = []
    basis_ids: list[str] = []
    next_id = 1
    for baseline_id in baseline_ids:
        basis_id = f"TB{next_id}"
        next_id += 1
        basis_ids.append(basis_id)
        basis_rows.append(
            f"| {basis_id} | 验收 | 00-baseline.md {baseline_id} | "
            f"证明 {baseline_id} 验收行为 | 高 | 是 | read-only | TS1 | 已覆盖 | 无 |"
        )
    for diff_path in diff_paths:
        basis_id = f"TB{next_id}"
        next_id += 1
        basis_ids.append(basis_id)
        basis_rows.append(
            f"| {basis_id} | diff | diff: {diff_path} | "
            f"证明 {diff_path} 的行为与兼容性 | 中 | 是 | read-only | TS1 | 已覆盖 | 无 |"
        )
    basis_text = "\n".join(basis_rows)
    scenario_sources = " ".join(basis_ids)
    return f"""# 测试验证轮次明细

## 1. 基本信息

- 轮次：{round_id}
- 测试模式：formal-gate
- 测试时间：2026-07-17
- 测试范围：报告提交主链路
- 环境与版本：local test / commit abc
- token / 角色类型：测试管理员
- 对应实现轮次：{implementation_round}
- 实现差异指纹：{fingerprint}
- 对应 Review 轮次：{review_round}

## 2. 测试结论

- 结论：通过
- 测试阶段是否完成：是
- 主要原因：全部必测来源和关键业务场景均验证通过
- 主要失败归因：无
- 建议返回阶段：无
- 复验条件：无

## 3. 测试依据覆盖

| 依据ID | 来源类型 | 来源定位 | 要证明的业务结果或风险 | 风险 | 必测 | Effect | 覆盖场景 | 覆盖结论 | 不适用/豁免事实与授权 |
|---|---|---|---|---|---|---|---|---|---|
{basis_text}

## 4. 测试场景清单

| 场景ID | 来源依据 | 业务场景 | 级别 | 前置条件 | 操作与测试数据 | 预期结果 | Effect | 结果 | 证据或原因 |
|---|---|---|---|---|---|---|---|---|---|
| TS1 | {scenario_sources} | 管理员提交报告并读取结果 | 关键 | 测试报告已创建 | 执行接口测试 reportId=1001 | 返回成功且业务结果可回查 | read-only | 通过 | E1；HTTP 200；evidence SHA-256 {evidence_sha} |

## 5. 执行记录

| 执行ID | 场景ID | 时间 | cwd / 环境 / 版本 | 命令/接口/观察点 | 退出码/协议结果 | 实际结果摘要 | Effect | 原始证据 | 证据 SHA-256 | 结论 |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | TS1 | 2026-07-17T10:00:00+08:00 | /repo / local / abc | api: POST /report/submit | HTTP 200 code=0 | 提交成功且结果字段正确 | read-only | `reports/evidence/e1.log` | {evidence_sha} | PASS |

## 6. 数据影响与恢复

- 计划 Effect：read-only
- 实际 Effect：read-only
- Effect 授权：不需要
- 本轮是否产生或修改数据：否
- 影响范围：无
- 清理、恢复或最终状态回查：只读场景无需恢复，已完成最终结果回查
- 恢复/回查证据及 SHA-256：不涉及，只读场景
- 遗留数据及影响：无

## 7. 缺口和阻塞

| 缺口编号 | 首次轮次 | 本轮场景 | 问题 | 影响级别 | 主要归因 | 当前状态 | 归因/关闭证据 | 返回阶段与复验条件 |
|---|---|---|---|---|---|---|---|---|
{gap_rows}

## 8. 工件清单

- 本轮证据文件清单及 SHA-256：reports/evidence/e1.log {evidence_sha}
- `reports/api-tests/` 关联文件：本轮无接口专项报告，已核对目录为空
"""


class WorkflowConsistencyTest(unittest.TestCase):
    def test_workflow_cli_exposes_full_lifecycle_phases(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "-h"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("to-alignment", completed.stdout)
        self.assertIn("confirm-baseline", completed.stdout)
        self.assertIn("confirm-schema", completed.stdout)
        self.assertIn("init-quick", completed.stdout)
        self.assertIn("to-design", completed.stdout)
        self.assertIn("to-tasks", completed.stdout)
        self.assertIn("to-implementation", completed.stdout)
        self.assertIn("quality-gate", completed.stdout)
        self.assertIn("implementation-start", completed.stdout)
        self.assertIn("implementation-precheck", completed.stdout)
        self.assertIn("implementation-verify", completed.stdout)
        self.assertIn("implementation-restart", completed.stdout)
        self.assertIn("implementation-complete", completed.stdout)
        self.assertIn("implementation-status", completed.stdout)
        self.assertIn("review-mark", completed.stdout)
        self.assertIn("review-status", completed.stdout)
        self.assertIn("test-run", completed.stdout)
        self.assertIn("test-mark", completed.stdout)
        self.assertIn("test-status", completed.stdout)
        self.assertIn("to-review", completed.stdout)
        self.assertIn("to-test", completed.stdout)
        self.assertIn("complete", completed.stdout)

    def test_technical_design_template_matches_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "technical-design-template.md").read_text(encoding="utf-8")
        for token in DESIGN_V5_REQUIRED_TOKENS:
            self.assertIn(token, text)
        self.assertIn("GGG_DESIGN_SCHEMA_VERSION: 5", text)
        self.assertNotIn("最小方案与复杂度准入", text)
        self.assertNotIn("SQL 字段风格参考", text)
        self.assertNotIn("旧逻辑与新逻辑差异", text)
        self.assertIn("字段类型、默认值、索引定义和最终 DDL 只在 `04-schema.sql` 维护", text)

    def test_task_v2_template_matches_compact_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "task-breakdown-template.md").read_text(encoding="utf-8")
        for token in TASK_V2_REQUIRED_TOKENS:
            self.assertIn(token, text)
        self.assertNotIn("推荐执行顺序", text)
        self.assertNotIn("- 复用范围：", text)
        self.assertIn("至少两个具体复用方", text)
        summary = extract_section(text, "## 3. 任务总览")
        self.assertIn("| 编号 | 开发任务 | 所属项目 | 依赖任务 |", summary)
        self.assertNotIn("来源依据", summary)
        self.assertNotIn("完成标准", summary)

    def test_quick_record_template_matches_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "quick-record-template.md").read_text(encoding="utf-8")
        for token in QUICK_RECORD_REQUIRED_TOKENS:
            self.assertIn(token, text)
        self.assertIn("- 代表性验收例：", text)
        self.assertIn("- 兼容性检查：", text)
        self.assertIn("现有调用方", text)
        self.assertIn("历史数据", text)
        self.assertIn("重复请求或重试", text)
        self.assertIn("### 4.1 代码质量自检", text)
        self.assertIn("### 4.2 运行验证", text)

    def test_quick_v2_boundary_requires_new_contract_fields(self) -> None:
        text = build_confirmed_quick_template()
        text = "\n".join(
            line
            for line in text.splitlines()
            if not any(
                line.startswith(prefix)
                for prefix in [
                    "- 推进模式：",
                    "- 路由依据：",
                    "- 代表性验收例：",
                    "- 失败 / 重复触发补充：",
                    "- 兼容性检查：",
                ]
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text + "\n", encoding="utf-8")
            errors = validate_quick_boundary_ready(path)

        message = "\n".join(errors)
        self.assertIn("必须明确推进模式", message)
        self.assertIn("路由依据缺少实质内容", message)
        self.assertIn("缺少强制字段：代表性验收例", message)
        self.assertIn("缺少强制字段：失败 / 重复触发补充", message)
        self.assertIn("缺少强制字段：兼容性检查", message)

    def test_quick_v2_boundary_rejects_shallow_example_and_empty_confirmed_question(self) -> None:
        text = (
            build_confirmed_quick_template()
            .replace(
                "- 代表性验收例：已存在 reportId 请求 -> 用户再次提交 -> 服务复用既有记录 -> 返回同一报告结果",
                "- 代表性验收例：通过",
            )
            .replace(
                "| Q1 | 重复提交口径 | 低风险 | 用户消息 2026-07-18 | 需确认幂等结果 | 返回既有记录 | 已确认 |",
                "| Q1 |  |  |  |  |  | 已确认 |",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_boundary_ready(path)

        message = "\n".join(errors)
        self.assertIn("代表性验收例仍为空或为模板占位", message)
        self.assertIn("Q1 影响级别非法或缺失", message)
        for field in ["疑问", "准确来源", "为什么不确定", "用户结论"]:
            self.assertIn(f"Q1 缺少实质内容: {field}", message)

    def test_quick_v1_boundary_keeps_legacy_compatibility(self) -> None:
        text = "\n".join(
            line
            for line in build_confirmed_quick_template().splitlines()
            if not any(
                line.startswith(prefix)
                for prefix in [
                    "<!-- GGG_QUICK_SCHEMA_VERSION:",
                    "- 推进模式：",
                    "- 路由依据：",
                    "- 代表性验收例：",
                    "- 失败 / 重复触发补充：",
                    "- 兼容性检查：",
                ]
            )
        )
        text = text.replace(
            "| 编号 | 疑问 | 影响级别 | 准确来源 | 为什么不确定 | 用户结论 | 状态 |",
            "| 编号 | 疑问 | 准确来源 | 为什么不确定 | 用户结论 | 状态 |",
        ).replace(
            "|---|---|---|---|---|---|---|",
            "|---|---|---|---|---|---|",
            1,
        ).replace(
            "| Q1 | 重复提交口径 | 低风险 | 用户消息 2026-07-18 | 需确认幂等结果 | 返回既有记录 | 已确认 |",
            "| Q1 | 重复提交口径 | 用户消息 2026-07-18 | 需确认幂等结果 | 返回既有记录 | 已确认 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text + "\n", encoding="utf-8")
            errors = validate_quick_boundary_ready(path)

        self.assertEqual([], errors)

    def test_quick_v2_rejects_invalid_mode_placeholders_and_bare_not_applicable(self) -> None:
        text = (
            build_confirmed_quick_template()
            .replace(
                "- 推进模式：quick（自动路由并已告知）",
                "- 推进模式：quick（自行判断）",
            )
            .replace(
                "- 最终边界确认：已确认（用户消息 2026-07-18）",
                "- 最终边界确认：已确认",
            )
            .replace("- 一句话目标：实现报告幂等提交", "- 一句话目标：待确认")
            .replace(
                "- 失败 / 重复触发补充：重复触发不新增记录，异常沿用现有错误口径",
                "- 失败 / 重复触发补充：不涉及",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_boundary_ready(path)

        message = "\n".join(errors)
        self.assertIn("必须明确推进模式", message)
        self.assertIn("最终边界确认必须记录用户消息定位或确认时间", message)
        self.assertIn("边界字段仍未收口: - 一句话目标", message)
        self.assertIn("失败 / 重复触发补充必须写明具体口径", message)

    def test_quick_v2_rejects_placeholder_confirmation_and_compatibility_values(self) -> None:
        text = (
            build_confirmed_quick_template()
            .replace(
                "- 最终边界确认：已确认（用户消息 2026-07-18）",
                "- 最终边界确认：已确认（待补充）",
            )
            .replace(
                "- 兼容性检查：现有调用方=无影响；历史数据=无影响；重复请求或重试=按既有记录返回",
                "- 兼容性检查：现有调用方=待确认；历史数据=无影响；重复请求或重试=按既有记录返回",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_boundary_ready(path)

        message = "\n".join(errors)
        self.assertIn("最终边界确认必须记录用户消息定位或确认时间", message)
        self.assertIn("兼容性检查缺少已收口项：现有调用方", message)

    def test_quick_v2_rejects_malformed_marker_and_duplicate_or_invalid_questions(self) -> None:
        text = (
            build_confirmed_quick_template()
            .replace(
                "<!-- GGG_QUICK_SCHEMA_VERSION: 2 -->",
                "<!-- GGG_QUICK_SCHEMA_VERSION: X -->",
            )
            .replace(
                "| Q1 | 重复提交口径 | 低风险 | 用户消息 2026-07-18 | 需确认幂等结果 | 返回既有记录 | 已确认 |",
                "| QX | 非法编号 | 低风险 | 用户消息 2026-07-18 | 需确认 | 采用现有口径 | 已确认 |\n"
                "| Q1 | 重复提交口径 | 低风险 | 用户消息 2026-07-18 | 需确认幂等结果 | 返回既有记录 | 已确认 |\n"
                "| Q1 | 重复提交范围 | 低风险 | PRD §3.2 | 范围有歧义 | 仅当前入口 | 已确认 |",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_boundary_ready(path)

        message = "\n".join(errors)
        self.assertIn("GGG_QUICK_SCHEMA_VERSION 标记畸形或重复", message)
        self.assertIn("非法编号: QX", message)
        self.assertIn("疑问编号重复: Q1", message)

    def test_quick_v2_allows_empty_question_ledger_after_removing_example_row(self) -> None:
        text = build_confirmed_quick_template().replace(
            "| Q1 | 重复提交口径 | 低风险 | 用户消息 2026-07-18 | 需确认幂等结果 | 返回既有记录 | 已确认 |\n",
            "",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_boundary_ready(path)

        self.assertEqual([], errors)

    def test_design_v4_allows_stateless_simple_contract_without_detail_or_diagram(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "02-design.md"
            path.write_text(build_design_doc_v4(), encoding="utf-8")
            errors = validate_design_doc(
                path,
                root / "interface-details",
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )

        self.assertEqual([], errors)

    def test_design_v4_does_not_require_non_mysql_detail_when_no_carrier_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "02-design.md"
            path.write_text(
                build_design_doc_v4(include_non_mysql_detail=False),
                encoding="utf-8",
            )
            errors = validate_design_doc(
                path,
                root / "interface-details",
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )

        self.assertEqual([], errors)

    def test_design_v4_precheck_allows_full_design_and_interface_detail_before_schema_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "02-design.md"
            path.write_text(
                build_design_doc_v4(
                    mysql_change=True,
                    state="SQL待确认",
                    detail_value="interface-details/02-interface-01-submit.md",
                ),
                encoding="utf-8",
            )
            detail_dir = root / "interface-details"
            detail_dir.mkdir()
            (detail_dir / "02-interface-01-submit.md").write_text(build_interface_detail(), encoding="utf-8")
            errors = validate_design_precheck(path, {"C1"}, set())

        self.assertEqual([], errors)

    def test_design_v5_and_interface_v3_close_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            details = root / "interface-details"
            details.mkdir()
            design.write_text(build_design_doc_v5(), encoding="utf-8")
            (details / "02-interface-01-submit.md").write_text(
                build_interface_detail_v3(),
                encoding="utf-8",
            )
            errors = validate_design_doc(
                design,
                details,
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )

        self.assertEqual([], errors)

    def test_design_v5_without_sql_or_independent_detail_stays_lightweight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            design.write_text(
                build_design_doc_v5(
                    detail_value="无需：简单内部调用不需要独立明细",
                ),
                encoding="utf-8",
            )
            errors = validate_design_doc(
                design,
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )

        self.assertEqual([], errors)

    def test_design_v5_interface_v3_rejects_every_main_detail_drift(self) -> None:
        base = build_interface_detail_v3()
        mutations = {
            "调用方/触发事件": base.replace(
                "| 调用方 / 触发事件 | 管理端提交 |",
                "| 调用方 / 触发事件 | 定时补偿任务 |",
            ),
            "契约类型": base.replace("| 契约类型 | HTTP |", "| 契约类型 | RPC |"),
            "契约标识": base.replace("| 契约标识 | POST /submit |", "| 契约标识 | POST /retry |"),
            "输入关键字段": base.replace(
                "| reportId | Body | long | 是 | 1001 | 外部 | 否 | 是 | 报告ID |",
                "| requestId | Body | long | 是 | 1001 | 外部 | 否 | 是 | 报告ID |",
            ).replace('{"reportId": 1001}', '{"requestId": 1001}'),
            "后端推导字段/来源": base.replace(
                "| userId | Context | long | 是 | 2001 | 登录态 | 是 | 否 | 当前用户 |",
                "| userId | Context | long | 是 | 2001 | 系统补充 | 是 | 否 | 当前用户 |",
            ),
            "禁止外部传字段": base.replace(
                "| userId | Context | long | 是 | 2001 | 登录态 | 是 | 否 | 当前用户 |",
                "| userId | Context | long | 是 | 2001 | 登录态 | 是 | 是 | 当前用户 |",
            ),
            "输出字段": base.replace(
                "| data.reportId | long | 报告ID |",
                "| data.taskId | long | 报告ID |",
            ).replace(
                '{"code": 200, "msg": "success", "data": {"reportId": 1001}}',
                '{"code": 200, "msg": "success", "data": {"taskId": 1001}}',
            ),
            "副作用": base.replace(
                "- 输出副作用：写入 report_record",
                "- 输出副作用：发布 report.completed 事件",
            ),
        }
        for field, detail_text in mutations.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                design = root / "02-design.md"
                details = root / "interface-details"
                details.mkdir()
                design.write_text(build_design_doc_v5(), encoding="utf-8")
                (details / "02-interface-01-submit.md").write_text(detail_text, encoding="utf-8")
                errors = validate_design_doc(
                    design,
                    details,
                    valid_claim_ids={"C1"},
                    eligible_claim_ids={"C1"},
                    transferred_question_ids=set(),
                )
                message = "\n".join(errors)
                self.assertIn(field, message)
                self.assertIn("契约主表不一致", message)

    def test_interface_v3_allows_no_synchronous_response_for_mq(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            details = root / "interface-details"
            details.mkdir()
            design.write_text(
                build_design_doc_v5(
                    caller="报告提交事件",
                    contract_type="MQ",
                    identifier="report.submit.v1",
                    output_fields="无",
                    side_effects="写入 report_record",
                ),
                encoding="utf-8",
            )
            (details / "02-interface-01-submit.md").write_text(
                build_interface_detail_v3(
                    caller="报告提交事件",
                    contract_type="MQ",
                    identifier="report.submit.v1",
                    no_response=True,
                ),
                encoding="utf-8",
            )
            errors = validate_design_doc(
                design,
                details,
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )
            detail_path = details / "02-interface-01-submit.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "```json\nnull\n```",
                    "```json\n[]\n```",
                ),
                encoding="utf-8",
            )
            empty_collection_errors = validate_design_doc(
                design,
                details,
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )

        self.assertEqual([], errors)
        self.assertEqual([], empty_collection_errors)

    def test_interface_v3_side_effect_requires_specific_value_or_no_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            details = root / "interface-details"
            details.mkdir()
            detail_path = details / "02-interface-01-submit.md"
            detail_path.write_text(
                build_interface_detail_v3(side_effects="无：只读查询不产生写入"),
                encoding="utf-8",
            )
            valid_errors = validate_interface_details_dir(details)
            detail_path.write_text(build_interface_detail_v3(side_effects="无"), encoding="utf-8")
            invalid_errors = validate_interface_details_dir(details)

        self.assertEqual([], valid_errors)
        self.assertIn("不能使用裸“无”", "\n".join(invalid_errors))

    def test_design_v4_and_interface_v2_remain_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            details = root / "interface-details"
            details.mkdir()
            design.write_text(
                build_design_doc_v4(detail_value="interface-details/02-interface-01-submit.md"),
                encoding="utf-8",
            )
            (details / "02-interface-01-submit.md").write_text(
                build_interface_detail(),
                encoding="utf-8",
            )
            errors = validate_design_doc(
                design,
                details,
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )

        self.assertEqual([], errors)

    def test_v4_design_and_v2_tasks_advance_to_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "init",
                    "--repo-root",
                    str(repo_root),
                    "--feature-name",
                    "v4-v2闭环",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            feature_dir = next((repo_root / "ggg" / "features").iterdir())
            (feature_dir / "00-baseline.md").write_text(build_confirmed_baseline(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "confirm-baseline",
                    "--feature-dir",
                    str(feature_dir),
                    "--source",
                    "用户确认",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "to-alignment",
                    "--feature-dir",
                    str(feature_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            source = repo_root / "src" / "ReportController.java"
            source.parent.mkdir()
            source.write_text("class ReportController {}\n", encoding="utf-8")
            (feature_dir / "01-research.md").write_text(
                build_research_doc("src/ReportController.java:1"),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "to-design",
                    "--feature-dir",
                    str(feature_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            (feature_dir / "02-design.md").write_text(
                build_design_doc_v4(include_non_mysql_detail=False),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "to-tasks",
                    "--feature-dir",
                    str(feature_dir),
                    "--design-confirmed",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            (feature_dir / "03-tasks.md").write_text(build_tasks_doc_v2(), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "to-implementation",
                    "--feature-dir",
                    str(feature_dir),
                    "--tasks-confirmed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)

    def test_task_v2_keeps_test_code_inside_functional_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(build_tasks_doc_v2(), encoding="utf-8")
            errors = validate_tasks_doc(
                path,
                valid_design_ids={"D1"},
                valid_claim_ids={"C1"},
                required_core_design_ids={"D1"},
            )

        self.assertEqual([], errors)

    def test_implementation_reads_task_ids_from_v2_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(build_tasks_doc_v2(), encoding="utf-8")

            task_ids = implementation_task_ids(path)

        self.assertEqual({"T1"}, task_ids)

    def test_task_v2_schema_reference_requires_persistence_code_landing(self) -> None:
        text = build_tasks_doc_v2("D1 / C1 / 04-schema.sql")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_tasks_doc(
                path,
                valid_design_ids={"D1"},
                valid_claim_ids={"C1"},
                schema_exists=True,
                required_core_design_ids={"D1"},
            )

        self.assertIn(
            "已引用 04-schema.sql，但对应任务缺少 Mapper/Repository/Entity 等持久化代码落点",
            "\n".join(errors),
        )

    def test_task_v2_schema_and_mapper_landing_pass_together(self) -> None:
        text = build_tasks_doc_v2("D1 / C1 / 04-schema.sql").replace(
            "src/main/java/demo/ReportService.java；src/test/java/demo/ReportServiceTest.java",
            "04-schema.sql；src/main/java/demo/ReportRecordMapper.java；"
            "src/test/java/demo/ReportServiceTest.java",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_tasks_doc(
                path,
                valid_design_ids={"D1"},
                valid_claim_ids={"C1"},
                schema_exists=True,
                required_core_design_ids={"D1"},
            )

        self.assertEqual([], errors)

    def test_task_v2_rejects_non_reusable_standalone_test_task(self) -> None:
        cases = [
            ("执行报告回归用例", "src/test/java/demo/ReportServiceTest.java"),
            ("新增 ReportServiceTest", "src/test/java/demo/ReportServiceTest.java"),
            ("补齐异常覆盖", "web/__tests__/report-submit.spec.ts"),
            ("实现测试基座", "test-support/src/main/java/demo/ContractTool.java"),
            ("实现测试基座", "ContractTestTool.java"),
        ]
        for task_name, files in cases:
            with self.subTest(task_name=task_name, files=files):
                text = (
                    build_tasks_doc_v2()
                    .replace("实现报告幂等提交能力", task_name)
                    .replace(
                        "src/main/java/demo/ReportService.java；src/test/java/demo/ReportServiceTest.java",
                        files,
                    )
                )
                self.assertIn(
                    "默认不应单拆测试任务",
                    "\n".join(validate_tasks_doc_v2_text(text)),
                )

    def test_task_v2_allows_independent_reusable_test_capability(self) -> None:
        text = (
            build_tasks_doc_v2()
            .replace("实现报告幂等提交能力", "实现可复用契约测试工具")
            .replace(
                "src/main/java/demo/ReportService.java；src/test/java/demo/ReportServiceTest.java",
                "src/testFixtures/java/demo/ContractTestTool.java；"
                "src/test/java/demo/ContractTestToolTest.java",
            )
            .replace(
                "- 主要实现内容：\n"
                "  - 按 reportId 查询既有记录，不存在时在当前事务内创建。\n"
                "  - 在 ReportServiceTest 中覆盖首次提交和重复提交。",
                "- 主要实现内容：\n"
                "  - ContractTestTool 统一构造契约请求、鉴权头和结果断言。\n"
                "  - ContractTestToolTest 覆盖数据隔离和清理。",
            )
            .replace(
                "- 代码边界：\n  - 保持现有 Controller 请求和响应契约，不新增异步链路。",
                "- 代码边界：\n"
                "  - 该契约测试工具供报告提交和报告重试两个契约测试复用。",
            )
            .replace(
                "必要测试代码：ReportServiceTest 覆盖首次提交和重复提交。",
                "必要测试代码：ContractTestToolTest 覆盖数据隔离和清理。",
            )
            .replace(
                "最小验证：运行 ReportServiceTest 的首次和重复提交用例。",
                "最小验证：运行 ContractTestToolTest 的数据隔离和清理用例。",
            )
        )
        self.assertEqual([], validate_tasks_doc_v2_text(text))

    def test_task_v2_reusable_test_capability_needs_asset_type_and_consumers(self) -> None:
        base = build_tasks_doc_v2().replace(
            "src/main/java/demo/ReportService.java；src/test/java/demo/ReportServiceTest.java",
            "src/test/java/demo/ReportServiceTest.java",
        )
        cases = [
            (
                "实现可复用契约测试工具",
                "- 代码边界：\n  - 该契约测试工具仅供当前报告提交测试使用。",
            ),
            (
                "补充共享回归用例",
                "- 代码边界：\n  - 该用例供报告提交和报告重试两个模块共同使用。",
            ),
            (
                "实现报告测试代码",
                "- 代码边界：\n  - 该任务不是契约测试工具，不能由多个模块复用。",
            ),
        ]
        for task_name, boundary in cases:
            with self.subTest(task_name=task_name):
                text = (
                    base
                    .replace("实现报告幂等提交能力", task_name)
                    .replace(
                        "- 代码边界：\n"
                        "  - 保持现有 Controller 请求和响应契约，不新增异步链路。",
                        boundary,
                    )
                )
                self.assertIn(
                    "必须同时写明测试资产类型和至少两个复用方",
                    "\n".join(validate_tasks_doc_v2_text(text)),
                )

    def test_task_v2_does_not_use_completion_text_as_reuse_evidence(self) -> None:
        text = (
            build_tasks_doc_v2()
            .replace(
                "src/main/java/demo/ReportService.java；src/test/java/demo/ReportServiceTest.java",
                "src/test/java/demo/ReportServiceTest.java",
            )
            .replace(
                "代码结果与关键行为：首次提交创建记录，重复提交返回同一记录。",
                "代码结果与关键行为：形成契约测试工具，供多个模块使用。",
            )
        )
        self.assertIn(
            "默认不应单拆测试任务",
            "\n".join(validate_tasks_doc_v2_text(text)),
        )

    def test_task_v2_requires_direct_unique_completion_items_per_task(self) -> None:
        base = build_tasks_doc_v2_with_second_task()
        code_result_line = (
            "  - 代码结果与关键行为：存在时返回报告，不存在时返回空结果。"
        )
        necessary_line = (
            "  - 必要测试代码：ReportQueryServiceTest 覆盖存在和不存在两类结果。"
        )
        verification_line = (
            "  - 最小验证：运行 ReportQueryServiceTest 的存在和不存在用例。"
        )
        cases = [
            (
                "missing code result",
                base.replace(f"{code_result_line}\n", "", 1),
                "T2 完成标准缺少直接子项: 代码结果与关键行为",
            ),
            (
                "duplicate code result",
                base.replace(code_result_line, f"{code_result_line}\n{code_result_line}", 1),
                "T2 完成标准的代码结果与关键行为子项重复",
            ),
            (
                "shallow code result",
                base.replace(code_result_line, "  - 代码结果与关键行为：完成", 1),
                "T2 完成标准缺少实质的代码结果与关键行为",
            ),
            (
                "generic completed code result",
                base.replace(
                    code_result_line,
                    "  - 代码结果与关键行为：代码已经开发完成。",
                    1,
                ),
                "T2 完成标准缺少实质的代码结果与关键行为",
            ),
            (
                "generic implemented feature result",
                base.replace(
                    code_result_line,
                    "  - 代码结果与关键行为：功能已经实现完成。",
                    1,
                ),
                "T2 完成标准缺少实质的代码结果与关键行为",
            ),
            (
                "missing necessary test",
                base.replace(f"{necessary_line}\n", "", 1),
                "T2 完成标准缺少直接子项: 必要测试代码",
            ),
            (
                "duplicate necessary test",
                base.replace(necessary_line, f"{necessary_line}\n{necessary_line}", 1),
                "T2 完成标准的必要测试代码子项重复",
            ),
            (
                "missing minimum verification",
                base.replace(f"{verification_line}\n", "", 1),
                "T2 完成标准缺少直接子项: 最小验证",
            ),
            (
                "empty minimum verification",
                base.replace(verification_line, "  - 最小验证：", 1),
                "T2 完成标准缺少可执行的最小验证",
            ),
            (
                "nested instead of direct necessary test",
                base.replace(necessary_line, f"    - {necessary_line.strip()[2:]}", 1),
                "T2 完成标准缺少直接子项: 必要测试代码",
            ),
        ]
        for name, text, expected in cases:
            with self.subTest(name=name):
                self.assertIn(expected, "\n".join(validate_tasks_doc_v2_text(text)))

    def test_task_v2_accepts_nested_values_under_direct_completion_items(self) -> None:
        text = (
            build_tasks_doc_v2()
            .replace(
                "  - 必要测试代码：ReportServiceTest 覆盖首次提交和重复提交。",
                "  - 必要测试代码：\n"
                "    - ReportServiceTest 覆盖首次提交和重复提交。",
            )
            .replace(
                "  - 最小验证：运行 ReportServiceTest 的首次和重复提交用例。",
                "  - 最小验证：\n"
                "    - 命令：`mvn -Dtest=ReportServiceTest test`\n"
                "    - 预期：首次和重复提交用例通过。",
            )
        )
        self.assertEqual([], validate_tasks_doc_v2_text(text))

    def test_task_v2_requires_test_code_and_executable_minimum_verification(self) -> None:
        for shallow, expected in [
            ("", "完成标准缺少实质的必要测试代码"),
            ("无", "完成标准缺少实质的必要测试代码"),
            ("不涉及", "必须附具体原因"),
            (
                "不涉及：具体原因 / 并入本 Txx：具体测试类、测试桩、数据构造或用例场景",
                "必须附具体原因",
            ),
        ]:
            with self.subTest(necessary_test=shallow):
                text = build_tasks_doc_v2().replace(
                    "必要测试代码：ReportServiceTest 覆盖首次提交和重复提交。",
                    f"必要测试代码：{shallow}",
                )
                self.assertIn(
                    expected,
                    "\n".join(validate_tasks_doc_v2_text(text)),
                )

        for shallow in [
            "代码审查确认",
            "运行测试通过",
            "执行所有测试",
            "运行所有测试用例",
            "执行相关测试用例",
            "验证业务接口",
            "验证业务接口响应正常",
            "执行对应测试类通过",
            "运行回归测试用例",
            "验证功能行为",
            "编译通过",
        ]:
            with self.subTest(minimum_verification=shallow):
                text = build_tasks_doc_v2().replace(
                    "最小验证：运行 ReportServiceTest 的首次和重复提交用例。",
                    f"最小验证：{shallow}",
                )
                self.assertIn(
                    "完成标准缺少可执行的最小验证",
                    "\n".join(validate_tasks_doc_v2_text(text)),
                )

    def test_task_test_artifact_detection_respects_name_boundaries(self) -> None:
        for production_file in [
            "src/main/java/demo/Latest.java",
            "src/main/java/demo/Contest.java",
        ]:
            self.assertFalse(is_test_artifact(production_file))
        for test_file in [
            "src/test/java/demo/ReportServiceTest.java",
            "web/__tests__/report-submit.spec.ts",
            "src/testFixtures/java/demo/SharedFixture.java",
            "test-support/src/main/java/demo/ContractTool.java",
            "testSupport/src/main/java/demo/ContractTool.java",
        ]:
            self.assertTrue(is_test_artifact(test_file))

    def test_task_v2_does_not_misclassify_functional_task_with_test_word(self) -> None:
        for task_name, production_file in [
            ("实现契约测试开关", "src/main/java/demo/ContractTestSwitch.java"),
            ("实现测试数据查询能力", "src/main/java/demo/TestDataQueryService.java"),
            ("实现测试用例管理能力", "src/main/java/demo/TestCaseManager.java"),
        ]:
            with self.subTest(task_name=task_name):
                text = (
                    build_tasks_doc_v2()
                    .replace("实现报告幂等提交能力", task_name)
                    .replace(
                        "src/main/java/demo/ReportService.java；src/test/java/demo/ReportServiceTest.java",
                        production_file,
                    )
                )
                self.assertEqual([], validate_tasks_doc_v2_text(text))

    def test_task_v2_rejects_high_risk_test_waiver(self) -> None:
        text = build_tasks_doc_v2().replace(
            "必要测试代码：ReportServiceTest 覆盖首次提交和重复提交。",
            "必要测试代码：不涉及：用户没有要求测试",
        )
        self.assertIn(
            "涉及高风险行为，必要测试代码不能写不涉及",
            "\n".join(validate_tasks_doc_v2_text(text)),
        )

    def test_task_v1_keeps_legacy_compatibility_without_v2_test_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(build_tasks_doc(), encoding="utf-8")
            errors = validate_tasks_doc(
                path,
                valid_design_ids={"D1"},
                valid_claim_ids={"C1"},
                required_core_design_ids={"D1"},
            )

        self.assertEqual([], errors)

    def test_task_schema_marker_cannot_fall_back_to_v1(self) -> None:
        text = "<!-- GGG_TASK_SCHEMA_VERSION: X -->\n" + build_tasks_doc()
        self.assertIn(
            "GGG_TASK_SCHEMA_VERSION 标记畸形或重复",
            "\n".join(validate_tasks_doc_v2_text(text)),
        )

    def test_implementation_quality_gate_rejects_unfilled_template(self) -> None:
        errors = validate_implementation_completion(
            ASSET_ROOT / "templates" / "implementation-log-template.md"
        )
        message = "\n".join(errors)
        self.assertIn("缺少有效实现轮次", message)

    def test_implementation_template_contains_all_session_fields(self) -> None:
        text = (ASSET_ROOT / "templates" / "implementation-log-template.md").read_text(encoding="utf-8")
        for field in [
            "- 实现状态：",
            "- 当前实现轮次：",
            "- 风险级别：",
            "- 预检状态：",
            "- 预检对应实现轮次：",
            "- 预检记录指纹：",
            "- 涉及 Git 仓库及编码基线：",
            "- 最终差异指纹：",
            "- Review 结论：",
            "- Review 对应实现轮次：",
            "- Review 对应差异指纹：",
        ]:
            self.assertIn(field, text)

    def test_implementation_skills_require_pre_code_design_check(self) -> None:
        implementation = (SKILLS_ROOT / "ggg-implementation" / "SKILL.md").read_text(encoding="utf-8")
        standard = (SKILLS_ROOT / "ggg-java-coding-standard" / "SKILL.md").read_text(encoding="utf-8")
        for token in ["主链路", "职责", "数据一致性", "性能", "失败边界"]:
            self.assertIn(token, standard)
        for profile in ["| `tiny` |", "| `normal` |", "| `high` |"]:
            self.assertIn(profile, implementation)
        self.assertNotIn("| high-risk |", implementation)
        self.assertIn("implementation-precheck", implementation)
        self.assertIn("implementation-restart", implementation)
        self.assertIn("不要扩写成第二份技术方案", implementation)
        self.assertIn("测试与验证", standard)
        self.assertIn("已经确认且代码事实一致的内容直接实施，不重复询问", standard)
        self.assertIn("实现偏离已确认内容", standard)

    def test_coding_workflow_requires_risk_driven_tests_or_explicit_waiver(self) -> None:
        implementation = (SKILLS_ROOT / "ggg-implementation" / "SKILL.md").read_text(encoding="utf-8")
        standard = (SKILLS_ROOT / "ggg-java-coding-standard" / "SKILL.md").read_text(encoding="utf-8")
        review = (SKILLS_ROOT / "ggg-code-review" / "SKILL.md").read_text(encoding="utf-8")
        review_checklist = (
            SKILLS_ROOT / "ggg-code-review" / "references" / "code-review-quality-checklist.md"
        ).read_text(encoding="utf-8")

        self.assertIn("应新增/更新最接近的自动化测试", implementation)
        self.assertIn("“用户未要求写测试”不是关键覆盖缺口的豁免理由", implementation)
        self.assertIn("无法合理自动化时允许显式豁免", standard)
        self.assertIn("高风险行为缺少自动化测试或明确豁免依据时属于验证缺口", review)
        self.assertIn("需要自动化测试，或记录可审计的豁免理由", review_checklist)

    def test_java_standard_is_single_source_for_coding_quality_rules(self) -> None:
        implementation = (SKILLS_ROOT / "ggg-implementation" / "SKILL.md").read_text(encoding="utf-8")
        standard = (SKILLS_ROOT / "ggg-java-coding-standard" / "SKILL.md").read_text(encoding="utf-8")
        review = (SKILLS_ROOT / "ggg-code-review" / "SKILL.md").read_text(encoding="utf-8")
        review_checklist = (
            SKILLS_ROOT / "ggg-code-review" / "references" / "code-review-quality-checklist.md"
        ).read_text(encoding="utf-8")

        self.assertIn("把本文件作为 GGG 唯一的 Java 后端代码规范", standard)
        self.assertIn("不重新解释业务，也不复制语言规范", implementation)
        self.assertIn("ggg-java-coding-standard", review)
        self.assertIn("不要重复编码规范", review_checklist)
        self.assertNotIn("fencing token", implementation)
        self.assertNotIn("fencing", review)

    def test_implementation_file_scope_includes_scripts_configs_and_build_files(self) -> None:
        for path in [
            "scripts/test_flow.py",
            "scripts/verify.sh",
            "config/payload.json",
            "templates/index.html",
            "Dockerfile",
            "Dockerfile.dev",
            "Makefile",
            "infra/main.tf",
            "web/icon.svg",
            "go.mod",
            ".env.example",
            "yarn.lock",
        ]:
            self.assertTrue(is_quality_file(path), path)
        self.assertFalse(is_quality_file("notes.md"))
        self.assertFalse(is_quality_file("implementation-state.json"))

    def test_implementation_path_parser_preserves_hidden_and_spaced_paths(self) -> None:
        self.assertEqual(
            {".github/workflows/ci.yml", "src/中文 文件.java"},
            extract_quality_paths(".github/workflows/ci.yml、`src/中文 文件.java`"),
        )

    def test_multi_repo_record_requires_exact_repository_label(self) -> None:
        actual = {"repoA/src/Main.java", "repoB/src/Main.java"}
        errors = compare_recorded_paths(actual, {"repoA/src/Main.java"}, {"repoA", "repoB"})
        self.assertIn("repoB/src/Main.java", "\n".join(errors))

        unqualified = compare_recorded_paths(actual, {"src/Main.java"}, {"repoA", "repoB"})
        self.assertIn("必须使用 仓库标签/相对路径", "\n".join(unqualified))

        extra = compare_recorded_paths(
            {"repoA/src/Main.java"},
            {"repoA/src/Main.java", "repoA/src/Fake.java"},
            {"repoA"},
        )
        self.assertIn("本轮未实际修改", "\n".join(extra))

    def test_implementation_round_uses_existing_record_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "05-implementation-log.md"
            record.write_text("| I7 | 历史实现 |\n", encoding="utf-8")
            self.assertEqual(8, next_round_number(record, {}))

    def test_current_implementation_round_excludes_unchanged_inherited_files(self) -> None:
        state = {
            "start_snapshot": {
                "repositories": [
                    {
                        "label": "demo",
                        "files": [
                            {"path": "src/Inherited.java", "digest": "same", "mode": "100644"},
                        ],
                    }
                ]
            },
            "repositories": [
                {
                    "root": "/repo",
                    "label": "demo",
                    "inherited_existing": ["src/Inherited.java"],
                    "round_adopted_existing": [],
                }
            ],
        }
        current = {
            "repositories": [
                {
                    "label": "demo",
                    "files": [
                        {"path": "src/Inherited.java", "digest": "same", "mode": "100644"},
                        {"path": "src/New.java", "digest": "new", "mode": "100644"},
                    ],
                }
            ]
        }
        self.assertEqual({"demo/src/New.java"}, current_round_paths(state, current))
        current["repositories"][0]["files"][0]["digest"] = "changed"
        self.assertEqual(
            {"demo/src/Inherited.java", "demo/src/New.java"},
            current_round_paths(state, current),
        )

    def test_implementation_quality_gate_accepts_complete_per_file_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "05-implementation-log.md"
            path.write_text(build_completed_implementation_log(), encoding="utf-8")
            errors = validate_implementation_completion(path)
        self.assertEqual([], errors)

    def test_full_implementation_gate_rejects_comment_evidence_from_other_file(self) -> None:
        text = build_completed_implementation_log().replace(
            "src/ReportController.java:24，说明重复提交返回既有结果的幂等边界",
            "src/OtherService.java:24，说明重复提交返回既有结果的幂等边界",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "05-implementation-log.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_implementation_completion(path)
        self.assertIn("关键逻辑注释证据引用了非本轮文件", "\n".join(errors))

    def test_full_implementation_gate_requires_latest_round_evidence(self) -> None:
        text = (
            build_completed_implementation_log()
            .replace(
                "| I1 | 2026-07-13 | T1 | ReportService 按 reportId 保存且重复提交返回既有结果；见 ReportController.java:24 | src/ReportController.java<br>src/ReportResponse.java | 编译通过 | 无 |",
                "| I1 | 2026-07-13 | T1 | ReportService 按 reportId 保存且重复提交返回既有结果；见 ReportController.java:24 | src/ReportController.java<br>src/ReportResponse.java | 编译通过 | 无 |\n"
                "| I2 | 2026-07-14 | T1 | 调整服务边界；见 NewService.java:20 | src/NewService.java | 编译通过 | 无 |",
            )
            .replace(
                "| I1 | mvn test | 通过 | 相关单测通过 |  |",
                "| I1 | mvn test | 通过 | 相关单测通过 |  |\n"
                "| I2 | mvn test | 通过 | I2 相关单测通过 |  |",
            )
            .replace(
                "| I1 | T1 | 主链路、接口契约、权限、异常日志、注释和格式测试 | src/ReportController.java:10、24；mvn test 通过 | 通过 | 无 |",
                "| I1 | T1 | 主链路、接口契约、权限、异常日志、注释和格式测试 | src/ReportController.java:10、24；mvn test 通过 | 通过 | 无 |\n"
                "| I2 | T1 | 服务边界、注释和格式测试 | src/NewService.java:20；mvn test 通过 | 通过 | 无 |",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "05-implementation-log.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_implementation_completion(path)
        self.assertIn("I2 缺少按轮次记录的关键规范证据", "\n".join(errors))

    def test_full_implementation_gate_rejects_any_failed_validation(self) -> None:
        text = build_completed_implementation_log().replace(
            "| I1 | mvn test | 通过 | 相关单测通过 |  |",
            "| I1 | mvn test | 通过 | 相关单测通过 |  |\n"
            "| I1 | mvn compile | 失败 | exit 1 | 编译失败 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "05-implementation-log.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_implementation_completion(path)
        self.assertIn("存在失败验证", "\n".join(errors))

    def test_implementation_quality_gate_detects_unfinished_planned_task(self) -> None:
        text = build_completed_implementation_log()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "05-implementation-log.md"
            path.write_text(text, encoding="utf-8")
            tasks = build_tasks_doc().replace(
                "\n\n## 4. 任务详情",
                "\n| T2 | 实现报告查询服务 | D1 / C1 | demo | src/main/java/demo/ReportQueryService.java | T1 | 可按 reportId 查询已保存报告 |\n\n## 4. 任务详情",
            )
            (Path(tmp) / "03-tasks.md").write_text(tasks, encoding="utf-8")
            errors = validate_implementation_completion(path)
        self.assertIn("T2", "\n".join(errors))

    def test_quick_quality_gate_accepts_complete_per_file_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(build_completed_quick_record(), encoding="utf-8")
            errors = validate_quick_implementation_completion(path)
        self.assertEqual([], errors)

    def test_quick_implementation_gate_rejects_failed_validation(self) -> None:
        text = build_completed_quick_record().replace("- 验证结果：通过", "- 验证结果：失败")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_implementation_completion(path)
        self.assertIn("仍存在失败验证", "\n".join(errors))

    def test_quick_implementation_gate_rejects_missing_key_logic_comment_evidence(self) -> None:
        text = build_completed_quick_record().replace(
            "- 关键逻辑注释证据：src/ReportController.java:24，说明重复提交返回既有结果的幂等边界",
            "- 关键逻辑注释证据：",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_implementation_completion(path)
        self.assertIn("缺少独立关键逻辑注释证据", "\n".join(errors))

    def test_quick_implementation_gate_rejects_explicitly_failed_comment_evidence(self) -> None:
        text = build_completed_quick_record().replace(
            "- 关键逻辑注释证据：src/ReportController.java:24，说明重复提交返回既有结果的幂等边界",
            "- 关键逻辑注释证据：未通过；src/ReportController.java:24 待补关键逻辑注释",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_implementation_completion(path)
        self.assertIn("关键逻辑注释证据仍明确为未通过", "\n".join(errors))

    def test_quick_implementation_gate_rejects_comment_evidence_from_other_file(self) -> None:
        text = build_completed_quick_record().replace(
            "- 修改文件：src/ReportController.java、src/ReportResponse.java",
            "- 修改文件：src/NewService.java",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_implementation_completion(path)
        self.assertIn("关键逻辑注释证据引用了非本轮文件", "\n".join(errors))

    def test_quick_implementation_gate_accepts_backticked_java_path_with_spaces(self) -> None:
        text = (
            build_completed_quick_record()
            .replace(
                "- 修改文件：src/ReportController.java、src/ReportResponse.java",
                "- 修改文件：`src/My Service.java`",
            )
            .replace(
                "- 关键逻辑注释证据：src/ReportController.java:24，说明重复提交返回既有结果的幂等边界",
                "- 关键逻辑注释证据：`src/My Service.java:24`，说明重复提交返回既有结果的幂等边界",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_implementation_completion(path)
        self.assertEqual([], errors)

    def test_quick_implementation_gate_accepts_complete_ddl_evidence(self) -> None:
        text = (
            build_completed_quick_record()
            .replace(
                "- 修改文件：src/ReportController.java、src/ReportResponse.java",
                "- 修改文件：src/schema.sql",
            )
            .replace(
                "- SQL/DDL 规范证据：不涉及 / `本轮SQL文件`＋参考表或统一兜底＋公共字段/例外＋生产方言与测试 schema 区分",
                "- SQL/DDL 规范证据：src/schema.sql；采用统一兜底公共字段；生产 MySQL DDL 与测试 schema 已区分",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_implementation_completion(path)
        self.assertEqual([], errors)

    def test_quick_implementation_gate_rejects_ddl_without_convention_evidence(self) -> None:
        text = (
            build_completed_quick_record()
            .replace(
                "- 修改文件：src/ReportController.java、src/ReportResponse.java",
                "- 修改文件：src/schema.sql",
            )
            .replace(
                "- SQL/DDL 规范证据：不涉及 / `本轮SQL文件`＋参考表或统一兜底＋公共字段/例外＋生产方言与测试 schema 区分",
                "- SQL/DDL 规范证据：不涉及",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_implementation_completion(path)
        self.assertIn("DDL 改动缺少 SQL/DDL 规范证据", "\n".join(errors))

    def test_quick_review_requires_independent_gate_a_evidence(self) -> None:
        text = build_completed_quick_record().replace(
            "| A | 目标、禁止项与行为 | 通过 | quick 边界与 src/ReportController.java:10-24 一致 |",
            "| A | 目标、禁止项与行为 | 通过 |  |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_review_evidence(path, {"src/ReportController.java"})
        self.assertIn("目标、禁止项与行为”缺少独立证据", "\n".join(errors))

    def test_quick_review_rejects_failed_gate_b_check(self) -> None:
        text = build_completed_quick_record().replace(
            "| B | 正确性、安全、失败边界与副作用 | 通过 | 独立检查幂等与异常边界 |",
            "| B | 正确性、安全、失败边界与副作用 | 有问题 | CR1：缺少幂等保护 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_review_evidence(path, {"src/ReportController.java"})
        self.assertIn("正确性、安全、失败边界与副作用”必须明确为通过", "\n".join(errors))

    def test_quick_review_rejects_diff_coverage_from_other_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(build_completed_quick_record(), encoding="utf-8")
            errors = validate_quick_review_evidence(path, {"src/NewService.java"})
        error_text = "\n".join(errors)
        self.assertIn("未覆盖本轮实际文件: src/NewService.java", error_text)
        self.assertIn("覆盖了非本轮文件", error_text)

    def test_quick_review_requires_all_actual_files_and_two_gates(self) -> None:
        text = build_completed_quick_record().replace(
            "| src/ReportResponse.java | 通过 | 通过 | src/ReportResponse.java:1-8 |",
            "",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_quick_review_evidence(
                path,
                {"src/ReportController.java", "src/ReportResponse.java"},
            )
        error_text = "\n".join(errors)
        self.assertIn("未覆盖本轮实际文件: src/ReportResponse.java", error_text)
        self.assertNotIn("幻觉审计", error_text)

    def test_quality_gate_cli_accepts_complete_quick_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(build_completed_quick_record(), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "quality-gate",
                    "--record",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("编码实现质量门禁已通过", completed.stdout)

    def test_implementation_precheck_uses_risk_profile_instead_of_fixed_five_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quick.md"
            path.write_text(
                """# Quick

### 3.1 编码前实现预检

| 轮次 | 检查面 | 预检结论 | 事实依据 | 状态 |
|---|---|---|---|---|
| I1 | 范围与主链路 | 只修改明确的展示文案，不改变行为契约 | src/View.tsx copy 常量 | 通过 |
| I1 | 验证策略 | 运行 formatter 并执行前端类型检查 | package.json scripts/typecheck | 通过 |
""",
                encoding="utf-8",
            )
            self.assertEqual(
                [],
                validate_implementation_precheck(path, "I1", "tiny"),
            )
            normal_errors = validate_implementation_precheck(path, "I1", "normal")
        self.assertIn("代码落点与职责", "\n".join(normal_errors))
        self.assertIn("数据、契约与失败边界", "\n".join(normal_errors))

    def test_implementation_start_rejects_unconfirmed_quick_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
            record = root / "quick.md"
            record.write_text(
                (ASSET_ROOT / "templates" / "quick-record-template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            started = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(0, started.returncode)
        self.assertIn("quick 边界尚未确认", started.stdout + started.stderr)

    def test_implementation_start_persists_tiny_risk_profile_and_two_precheck_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
            record = root / "quick.md"
            record.write_text(
                build_confirmed_quick_template(),
                encoding="utf-8",
            )
            started = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                    "--risk-profile",
                    "tiny",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, started.returncode, started.stdout + started.stderr)
            state = json.loads((root / "implementation-state.json").read_text(encoding="utf-8"))
            self.assertEqual("tiny", state["risk_profile"])
            current_rows = [
                line for line in record.read_text(encoding="utf-8").splitlines()
                if line.startswith("| I1 |")
            ]
            self.assertEqual(2, len(current_rows))
            self.assertTrue(any("范围与主链路" in line for line in current_rows))
            self.assertTrue(any("验证策略" in line for line in current_rows))

    def test_full_implementation_start_defaults_to_remaining_tasks_then_requires_explicit_rework_task(self) -> None:
        tasks = """# 任务拆分

## 3. 编码任务

| 编号 | 开发任务 | 来源依据 | 所属项目 | 预计修改文件/符号 | 依赖任务 | 完成标准 |
|---|---|---|---|---|---|---|
| T1 | 实现服务 | D1 | demo | Service.java | - | 服务可用 |
| T2 | 接入入口 | D1 | demo | Controller.java | T1 | 接口可用 |
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            remaining_feature = root / "remaining"
            remaining_feature.mkdir()
            remaining_record = remaining_feature / "05-implementation-log.md"
            remaining_record.write_text(build_completed_implementation_log(), encoding="utf-8")
            (remaining_feature / "03-tasks.md").write_text(tasks, encoding="utf-8")
            started = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(remaining_record),
                    "--repo-root",
                    str(repo),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, started.returncode, started.stdout + started.stderr)
            remaining_state = json.loads(
                (remaining_feature / "implementation-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(["T2"], remaining_state["selected_tasks"])
            self.assertEqual(["T1"], remaining_state["completed_task_ids"])

            rework_feature = root / "rework"
            rework_feature.mkdir()
            rework_record = rework_feature / "05-implementation-log.md"
            rework_record.write_text(
                build_completed_implementation_log().replace(
                    "| I1 | 2026-07-13 | T1 |",
                    "| I1 | 2026-07-13 | T1, T2 |",
                ),
                encoding="utf-8",
            )
            (rework_feature / "03-tasks.md").write_text(tasks, encoding="utf-8")
            implicit = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(rework_record),
                    "--repo-root",
                    str(repo),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, implicit.returncode)
            self.assertIn("均已完成", implicit.stdout + implicit.stderr)

            explicit = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(rework_record),
                    "--repo-root",
                    str(repo),
                    "--task",
                    "T1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, explicit.returncode, explicit.stdout + explicit.stderr)
            rework_state = json.loads(
                (rework_feature / "implementation-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(["T1"], rework_state["selected_tasks"])
            self.assertEqual(["T1", "T2"], rework_state["completed_task_ids"])

    def test_implementation_precheck_rejects_code_changed_after_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=True,
                capture_output=True,
            )
            fill_completed_implementation_precheck(record)
            (repo / "Feature.java").write_text("class Feature {}\n", encoding="utf-8")

            precheck = run_implementation_precheck(record)
            self.assertNotEqual(0, precheck.returncode)
            self.assertIn("必须在本轮新增代码修改之前完成", precheck.stdout)

    def test_implementation_complete_requires_locked_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=True,
                capture_output=True,
            )
            (repo / "Feature.java").write_text("class Feature {}\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-complete",
                    "--record",
                    str(record),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, completed.returncode)
        self.assertIn("缺少已通过的编码前实现预检", completed.stderr + completed.stdout)

    def test_implementation_complete_rejects_quick_boundary_changed_after_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=True,
                capture_output=True,
            )
            state = json.loads((root / "implementation-state.json").read_text(encoding="utf-8"))
            self.assertEqual(
                quick_boundary_fingerprint(record),
                state["quick_boundary_fingerprint"],
            )

            record.write_text(
                record.read_text(encoding="utf-8").replace(
                    "- 一句话目标：实现报告幂等提交",
                    "- 一句话目标：实现报告异步提交",
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-complete",
                    "--record",
                    str(record),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn(
            "quick 边界在本实现轮次开始后发生变化",
            completed.stderr + completed.stdout,
        )

    def test_implementation_complete_rejects_modified_precheck_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=True,
                capture_output=True,
            )
            fill_completed_implementation_precheck(record)
            precheck = run_implementation_precheck(record)
            self.assertEqual(0, precheck.returncode, precheck.stdout + precheck.stderr)

            text = record.read_text(encoding="utf-8").replace(
                "ReportController 负责接口边界，ReportService 负责幂等保存",
                "ReportController 和 ReportService 共同处理本轮实现",
            )
            record.write_text(text, encoding="utf-8")
            (repo / "Feature.java").write_text("class Feature {}\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-complete",
                    "--record",
                    str(record),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("预检记录在通过后发生变化", completed.stderr + completed.stdout)

            restarted = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-restart",
                    "--record",
                    str(record),
                    "--reason",
                    "核心实现草图在编码中发生变化",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, restarted.returncode, restarted.stdout + restarted.stderr)
            self.assertIn("已废弃实现轮次 I1 并开启 I2", restarted.stdout)
            state = json.loads((root / "implementation-state.json").read_text(encoding="utf-8"))
            self.assertEqual("I2", state["round"])
            self.assertEqual("I1", state["superseded_rounds"][0]["round"])
            self.assertEqual(
                current_snapshot(state)["fingerprint"],
                state["start_snapshot"]["fingerprint"],
            )
            fill_completed_implementation_precheck(record, "I2")
            second_precheck = run_implementation_precheck(record)
            self.assertEqual(
                0,
                second_precheck.returncode,
                second_precheck.stdout + second_precheck.stderr,
            )

    def test_implementation_complete_requires_fresh_snapshot_verification_or_waiver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=True,
                capture_output=True,
            )
            fill_completed_implementation_precheck(record)
            precheck = run_implementation_precheck(record)
            self.assertEqual(0, precheck.returncode, precheck.stdout + precheck.stderr)
            (repo / "src").mkdir()
            controller = repo / "src" / "ReportController.java"
            controller.write_text("class ReportController {}\n", encoding="utf-8")
            (repo / "src" / "ReportResponse.java").write_text("class ReportResponse {}\n", encoding="utf-8")

            missing = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-complete",
                    "--record",
                    str(record),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("当前代码快照缺少成功验证", missing.stdout + missing.stderr)

            verified = run_implementation_verify(record, repo)
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
            state = json.loads((root / "implementation-state.json").read_text(encoding="utf-8"))
            self.assertEqual("passed", state["verification_runs"][-1]["result"])
            self.assertRegex(state["verification_runs"][-1]["stdout_sha256"], r"^[0-9a-f]{64}$")

            controller.write_text("class ReportController { int changed; }\n", encoding="utf-8")
            stale = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-complete",
                    "--record",
                    str(record),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, stale.returncode)
            self.assertIn("当前代码快照缺少成功验证", stale.stdout + stale.stderr)

            waived = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-complete",
                    "--record",
                    str(record),
                    "--verification-waiver",
                    "CI 依赖服务不可达；保留本地编译证据并在 CI 恢复后复跑",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, waived.returncode, waived.stdout + waived.stderr)
            state = json.loads((root / "implementation-state.json").read_text(encoding="utf-8"))
            self.assertIn("CI 依赖服务不可达", state["verification_waiver"]["reason"])

    def test_implementation_restart_recovers_legacy_in_progress_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=True,
                capture_output=True,
            )
            state_path = root / "implementation-state.json"
            legacy_state = json.loads(state_path.read_text(encoding="utf-8"))
            legacy_state["schema_version"] = 4
            legacy_state.pop("start_snapshot", None)
            legacy_state.pop("precheck", None)
            state_path.write_text(
                json.dumps(legacy_state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (repo / "Feature.java").write_text("class Feature {}\n", encoding="utf-8")

            restarted = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-restart",
                    "--record",
                    str(record),
                    "--reason",
                    "升级前的进行中会话已经存在代码修改",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, restarted.returncode, restarted.stdout + restarted.stderr)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(7, state["schema_version"])
            self.assertEqual("I2", state["round"])
            self.assertEqual(
                quick_boundary_fingerprint(record),
                state["quick_boundary_fingerprint"],
            )
            self.assertEqual(4, sum(
                1 for line in record.read_text(encoding="utf-8").splitlines()
                if line.startswith("| I2 |")
            ))

    def test_implementation_session_locks_diff_and_invalidates_review_after_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            start = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, start.returncode, start.stdout + start.stderr)
            fill_completed_implementation_precheck(record)
            precheck = run_implementation_precheck(record)
            self.assertEqual(0, precheck.returncode, precheck.stdout + precheck.stderr)

            (repo / "src").mkdir()
            (repo / "src" / "ReportController.java").write_text("class ReportController {}\n", encoding="utf-8")
            (repo / "src" / "ReportResponse.java").write_text("class ReportResponse {}\n", encoding="utf-8")
            verified = run_implementation_verify(record, repo)
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
            complete = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "implementation-complete", "--record", str(record)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, complete.returncode, complete.stdout + complete.stderr)
            self.assertIn("最终差异指纹", complete.stdout)

            review_text = (
                record.read_text(encoding="utf-8")
                .replace("- Review Gate A：未执行", "- Review Gate A：通过")
                .replace("- Review Gate B：未执行", "- Review Gate B：通过")
            )
            record.write_text(review_text, encoding="utf-8")
            review = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "review-mark",
                    "--record",
                    str(record),
                    "--result",
                    "passed",
                    "--reviewer-mode",
                    "fresh-review",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, review.returncode, review.stdout + review.stderr)
            state = json.loads((root / "implementation-state.json").read_text(encoding="utf-8"))
            self.assertEqual("fresh-review", state["review"]["reviewer_mode"])
            self.assertIn("- Review 方式：fresh-review", record.read_text(encoding="utf-8"))

            (repo / "src" / "ReportController.java").write_text("class ReportController { int changed; }\n", encoding="utf-8")
            stale = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "implementation-status", "--record", str(record)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, stale.returncode)
            self.assertIn("[STALE]", stale.stdout)

            review_stale = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "review-status", "--record", str(record), "--require-passed"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, review_stale.returncode)

    def test_implementation_session_rejects_workflow_document_only_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=True,
                capture_output=True,
            )
            fill_completed_implementation_precheck(record)
            precheck = run_implementation_precheck(record)
            self.assertEqual(0, precheck.returncode, precheck.stdout + precheck.stderr)
            verified = run_implementation_verify(record, repo)
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
            (repo / "notes.md").write_text("workflow notes only\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "implementation-complete", "--record", str(record)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("没有检测到代码或配置改动", completed.stderr + completed.stdout)

    def test_git_snapshot_handles_unicode_paths_and_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            script = repo / "script.sh"
            script.write_text("#!/bin/sh\necho base\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "script.sh"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            unicode_file = repo / "中文 文件.java"
            unicode_file.write_text("class Demo {}\n", encoding="utf-8")
            dirty = initial_dirty_snapshot(repo)
            self.assertIn("中文 文件.java", dirty)
            self.assertNotEqual("<missing>", dirty["中文 文件.java"]["digest"])

            unicode_file.unlink()
            base_head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            state = {
                "schema_version": 3,
                "repositories": [
                    {"root": str(repo), "label": "demo", "base_head": base_head, "initial_dirty": {}}
                ],
            }
            script.write_text("#!/bin/sh\necho changed\n", encoding="utf-8")
            script.chmod(0o755)
            executable = current_snapshot(state)["fingerprint"]
            script.chmod(0o644)
            non_executable = current_snapshot(state)["fingerprint"]
            self.assertNotEqual(executable, non_executable)

    def test_initial_dirty_rename_does_not_leak_old_path_into_session_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            old_path = repo / "Old.java"
            old_path.write_text("class Old {}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "Old.java"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
            base_head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            subprocess.run(["git", "-C", str(repo), "mv", "Old.java", "新文件.java"], check=True)
            initial = initial_dirty_snapshot(repo)
            (repo / "新文件.java").write_text("class Old { int changed; }\n", encoding="utf-8")

            changed = changed_paths(
                {"root": str(repo), "base_head": base_head, "initial_dirty": initial}
            )
            self.assertEqual({"新文件.java"}, changed)

    def test_adopted_existing_file_is_included_while_unrelated_dirty_file_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            for name in ["Feature.java", "Unrelated.java"]:
                (repo / name).write_text(f"class {Path(name).stem} {{}}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
            base_head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            (repo / "Feature.java").write_text("class Feature { int done; }\n", encoding="utf-8")
            (repo / "Unrelated.java").write_text("class Unrelated { int userChange; }\n", encoding="utf-8")
            initial = initial_dirty_snapshot(repo)
            repo_state = {
                "root": str(repo.resolve()),
                "label": "demo",
                "base_head": base_head,
                "initial_dirty": initial,
            }
            adopted = resolve_adopted_existing_files([repo_state], ["Feature.java"])
            repo_state["adopted_existing"] = sorted(adopted[str(repo.resolve())])

            self.assertEqual({"Feature.java"}, changed_paths(repo_state))

    def test_implementation_start_cli_records_adopted_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            feature = repo / "Feature.java"
            feature.write_text("class Feature {}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
            feature.write_text("class Feature { int existing; }\n", encoding="utf-8")

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            started = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                    "--adopt-existing-file",
                    "Feature.java",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, started.returncode, started.stdout + started.stderr)
            self.assertIn("已接管已有实现: Feature.java", started.stdout)
            state = json.loads((root / "implementation-state.json").read_text(encoding="utf-8"))
            self.assertEqual(["Feature.java"], state["repositories"][0]["adopted_existing"])
            self.assertEqual({"Feature.java"}, changed_paths(state["repositories"][0]))

    def test_adopt_existing_rejects_clean_file_and_requires_absolute_path_for_multi_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            states = []
            for name in ["repo-a", "repo-b"]:
                repo = root / name
                repo.mkdir()
                subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
                subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
                (repo / "Clean.java").write_text("class Clean {}\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
                subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
                states.append(
                    {
                        "root": str(repo.resolve()),
                        "label": name,
                        "base_head": subprocess.run(
                            ["git", "-C", str(repo), "rev-parse", "HEAD"],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip(),
                        "initial_dirty": initial_dirty_snapshot(repo),
                    }
                )

            with self.assertRaisesRegex(SystemExit, "必须使用绝对路径"):
                resolve_adopted_existing_files(states, ["Clean.java"])
            with self.assertRaisesRegex(SystemExit, "不是 Git 脏文件"):
                resolve_adopted_existing_files([states[0]], ["Clean.java"])

    def test_full_implementation_session_uses_task_and_completion_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            feature = root / "feature"
            feature.mkdir()
            record = feature / "05-implementation-log.md"
            record.write_text(
                (ASSET_ROOT / "templates" / "implementation-log-template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (feature / "03-tasks.md").write_text(build_tasks_doc(), encoding="utf-8")

            start = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, start.returncode, start.stdout + start.stderr)
            self.assertIn("I1", start.stdout)

            record.write_text(build_completed_implementation_log(), encoding="utf-8")
            fill_completed_implementation_precheck(record)
            precheck = run_implementation_precheck(record)
            self.assertEqual(0, precheck.returncode, precheck.stdout + precheck.stderr)
            (repo / "src").mkdir()
            (repo / "src" / "ReportController.java").write_text("class ReportController {}\n", encoding="utf-8")
            (repo / "src" / "ReportResponse.java").write_text("class ReportResponse {}\n", encoding="utf-8")
            verified = run_implementation_verify(record, repo)
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)

            complete = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "implementation-complete", "--record", str(record)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, complete.returncode, complete.stdout + complete.stderr)
            completed_text = record.read_text(encoding="utf-8")
            self.assertIn("- 实现状态：已完成", completed_text)
            self.assertRegex(completed_text, r"- 最终差异指纹：[0-9a-f]{64}")

    def test_implementation_session_requires_frontend_file_quality_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "demo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

            record = root / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "implementation-start",
                    "--record",
                    str(record),
                    "--repo-root",
                    str(repo),
                ],
                check=True,
                capture_output=True,
            )
            fill_completed_implementation_precheck(record)
            precheck = run_implementation_precheck(record)
            self.assertEqual(0, precheck.returncode, precheck.stdout + precheck.stderr)
            (repo / "src").mkdir()
            (repo / "src" / "ReportController.java").write_text("class ReportController {}\n", encoding="utf-8")
            (repo / "src" / "ReportResponse.java").write_text("class ReportResponse {}\n", encoding="utf-8")
            (repo / "front").mkdir()
            (repo / "front" / "index.tsx").write_text("export default () => null;\n", encoding="utf-8")
            verified = run_implementation_verify(record, repo)
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)

            completed = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "implementation-complete", "--record", str(record)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("front/index.tsx", completed.stdout)

    def test_review_completion_requires_gate_a_gate_b_and_complete_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(build_completed_review_index(), encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(build_completed_review_round(), encoding="utf-8")
            errors = validate_code_review_completion(
                index,
                rounds,
                actual_paths={"src/ReportController.java"},
                expected_implementation_round="I1",
                expected_fingerprint="a" * 64,
                expected_input_fingerprint="b" * 64,
            )
        self.assertEqual([], errors)

    def test_full_review_rejects_stale_implementation_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(build_completed_review_index(), encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(build_completed_review_round(), encoding="utf-8")
            errors = validate_code_review_completion(
                index,
                rounds,
                actual_paths={"src/ReportController.java"},
                expected_implementation_round="I1",
                expected_fingerprint="different",
            )
        self.assertIn("实现差异指纹与当前完成快照不一致", "\n".join(errors))

    def test_full_review_rejects_empty_round_binding_without_session_context(self) -> None:
        review = (
            build_completed_review_round()
            .replace("- 对应实现轮次：I1", "- 对应实现轮次：")
            .replace(f"- 实现差异指纹：{'a' * 64}", "- 实现差异指纹：")
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(build_completed_review_index(), encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(review, encoding="utf-8")
            errors = validate_code_review_completion(index, rounds)
        error_text = "\n".join(errors)
        self.assertIn("缺少有效对应实现轮次", error_text)
        self.assertIn("缺少有效的 64 位实现差异指纹", error_text)

    def test_full_review_rejects_incomplete_diff_manifest(self) -> None:
        review = build_completed_review_round(paths=("src/ReportController.java",)).replace(
            "- 实际 diff 文件数：1",
            "- 实际 diff 文件数：2",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(build_completed_review_index(), encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(review, encoding="utf-8")
            errors = validate_code_review_completion(
                index,
                rounds,
                actual_paths={"src/ReportController.java", "src/schema.sql"},
                expected_implementation_round="I1",
                expected_fingerprint="a" * 64,
            )
        self.assertIn("未覆盖真实 Diff 文件: src/schema.sql", "\n".join(errors))

    def test_full_review_accepts_complete_multi_file_diff_manifest(self) -> None:
        review = build_completed_review_round(
            paths=("src/ReportController.java", "src/schema.sql"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(build_completed_review_index(), encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(review, encoding="utf-8")
            errors = validate_code_review_completion(
                index,
                rounds,
                actual_paths={"src/ReportController.java", "src/schema.sql"},
                expected_implementation_round="I1",
                expected_fingerprint="a" * 64,
            )
        self.assertEqual([], errors)

    def test_full_review_rejects_open_must_fix_problem(self) -> None:
        issue = (
            "| CR1 | 必须修 | A | src/ReportController.java:12 | "
            "未校验归属 | 可能越权 | 增加服务端归属校验 | open |"
        )
        review = build_completed_review_round(issue_rows=issue)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(build_completed_review_index(), encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(review, encoding="utf-8")
            errors = validate_code_review_completion(
                index,
                rounds,
                actual_paths={"src/ReportController.java"},
                expected_implementation_round="I1",
                expected_fingerprint="a" * 64,
            )
        self.assertIn("CR1 仍是未关闭的必须修问题", "\n".join(errors))

    def test_full_review_rejects_gate_a_evidence_truthfulness_failure(self) -> None:
        review = build_completed_review_round().replace(
            "| 结论与验证证据真实性 | 通过 | T1、D1 与完整 diff 独立核对 | 无 |",
            "| 结论与验证证据真实性 | 有问题 | 发现验证结论没有原始证据 | CR1 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(build_completed_review_index(), encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(review, encoding="utf-8")
            errors = validate_code_review_completion(index, rounds)
        self.assertIn("Gate A“结论与验证证据真实性”未通过", "\n".join(errors))

    def test_full_review_rejects_index_and_round_mismatch(self) -> None:
        index_text = build_completed_review_index().replace("- 最新轮次：R1", "- 最新轮次：R2")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(index_text, encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(build_completed_review_round(), encoding="utf-8")
            errors = validate_code_review_completion(index, rounds)
        self.assertIn("最新轮次与 Review 明细不一致", "\n".join(errors))

    def test_full_review_rejects_open_must_fix_problem_in_index(self) -> None:
        index_text = build_completed_review_index(
            issue_rows=(
                "| CR1 | R1 | R1 | 必须修 | A | "
                "Mapper 缺少租户条件 | open |  |"
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(index_text, encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(build_completed_review_round(), encoding="utf-8")
            errors = validate_code_review_completion(index, rounds)
        self.assertIn("06-code-review.md CR1 仍是未关闭的必须修问题", "\n".join(errors))

    def test_full_review_requires_open_cr_to_continue_into_next_round(self) -> None:
        open_issue = (
            "| CR1 | 必须修 | A | src/ReportController.java:12 | "
            "未校验归属 | 可能越权 | 增加服务端归属校验 | open |"
        )
        ledger = (
            "| CR1 | R1 | R2 | 必须修 | A | "
            "未校验归属 | open |  |"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(
                build_completed_review_index(round_id="R2", issue_rows=ledger),
                encoding="utf-8",
            )
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(
                build_completed_review_round(issue_rows=open_issue),
                encoding="utf-8",
            )
            (rounds / "review-r02.md").write_text(
                build_completed_review_round(round_id="R2"),
                encoding="utf-8",
            )
            errors = validate_code_review_completion(
                index,
                rounds,
                actual_paths={"src/ReportController.java"},
                expected_implementation_round="I1",
                expected_fingerprint="a" * 64,
            )
        self.assertIn("最新 Review 未继承上轮未关闭问题: CR1", "\n".join(errors))

    def test_review_input_and_artifact_fingerprints_cover_authoritative_inputs_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            record = feature / "05-implementation-log.md"
            record.write_text(build_completed_implementation_log(), encoding="utf-8")
            baseline = feature / "00-baseline.md"
            baseline.write_text("baseline-v1\n", encoding="utf-8")
            (feature / "06-code-review.md").write_text(
                build_completed_review_index(),
                encoding="utf-8",
            )
            rounds = feature / "review-rounds"
            rounds.mkdir()
            round_path = rounds / "review-r01.md"
            round_path.write_text(build_completed_review_round(), encoding="utf-8")

            input_v1 = review_input_fingerprint(record, "a" * 64)
            artifact_v1 = review_artifact_fingerprint(record)
            baseline.write_text("baseline-v2\n", encoding="utf-8")
            self.assertNotEqual(input_v1, review_input_fingerprint(record, "a" * 64))
            round_path.write_text(
                round_path.read_text(encoding="utf-8").replace(
                    "- 剩余风险：无",
                    "- 剩余风险：仍需观察历史数据",
                ),
                encoding="utf-8",
            )
            self.assertNotEqual(artifact_v1, review_artifact_fingerprint(record))

    def test_quick_review_input_fingerprint_covers_schema_and_interface_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            record = feature / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            initial = review_input_fingerprint(record, "a" * 64)

            schema = feature / "04-schema.sql"
            schema.write_text("-- schema v1\n", encoding="utf-8")
            with_schema = review_input_fingerprint(record, "a" * 64)
            self.assertNotEqual(initial, with_schema)

            interface_dir = feature / "interface-details"
            interface_dir.mkdir()
            interface_path = interface_dir / "02-interface-01-submit.md"
            interface_path.write_text("# contract v1\n", encoding="utf-8")
            with_contract = review_input_fingerprint(record, "a" * 64)
            self.assertNotEqual(with_schema, with_contract)

            interface_path.write_text("# contract v2\n", encoding="utf-8")
            self.assertNotEqual(
                with_contract,
                review_input_fingerprint(record, "a" * 64),
            )

    def test_technical_design_template_examples_do_not_satisfy_traceability(self) -> None:
        errors = validate_design_doc(
            ASSET_ROOT / "templates" / "technical-design-template.md",
            valid_claim_ids={"C1"},
        )
        error_text = "\n".join(errors)

        self.assertIn("缺少 Dxx 设计ID", error_text)
        self.assertIn("缺少 Cxx 来源引用", error_text)

    def test_baseline_template_matches_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "baseline-template.md").read_text(encoding="utf-8")
        for token in BASELINE_REQUIRED_TOKENS:
            self.assertIn(token, text)

    def test_prd_intake_questions_recommend_without_silent_guessing(self) -> None:
        skill = skill_path("ggg-prd-intake", "SKILL.md").read_text(encoding="utf-8")
        question_template = (WORKFLOW_ROOT / "references" / "question-output-template.md").read_text(encoding="utf-8")

        self.assertIn("每项用户可见内容只包含", skill)
        self.assertIn("高影响阻塞问题一轮一问", skill)
        self.assertIn("低风险独立问题", skill)
        self.assertIn("代码现状不等于用户需求", skill)
        self.assertIn("暂无可靠推荐", question_template)
        self.assertIn("代码现状不等于用户需求", question_template)
        self.assertIn("**当前疑问**", question_template)
        self.assertIn("**推荐理解**", question_template)
        self.assertNotIn("**已知事实**", question_template)
        self.assertNotIn("**推荐依据**", question_template)
        self.assertNotIn("**理解错误的影响**", question_template)
        self.assertNotIn("**确认问题**", question_template)

    def test_prd_intake_avoids_redundant_mode_and_local_baseline_confirmation(self) -> None:
        skill = skill_path("ggg-prd-intake", "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("自动路由 quick / full 并告知", skill)
        self.assertIn("路由清楚时直接继续，不等待用户重复确认", skill)
        self.assertIn("同模块低风险独立问题可以一轮合并 2-3 个", skill)
        self.assertIn("局部明确修正", skill)
        self.assertIn("不重复完整主链路复述", skill)

    def test_baseline_clarification_gate_blocks_draft(self) -> None:
        template = (ASSET_ROOT / "templates" / "baseline-template.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "00-baseline.md"
            path.write_text(template.replace("- 主项目：", "- 主项目：demo"), encoding="utf-8")

            errors = validate_baseline_doc(path)

        message = "\n".join(errors)
        self.assertIn("基线状态必须为“已确认”", message)
        self.assertIn("缺少用户最终反向确认记录", message)

    def test_baseline_clarification_gate_accepts_confirmed_ledger(self) -> None:
        confirmed = build_confirmed_baseline()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "00-baseline.md"
            path.write_text(confirmed, encoding="utf-8")

            errors = validate_baseline_doc(path)

        self.assertEqual([], errors)

    def test_confirmed_empty_baseline_is_rejected(self) -> None:
        template = (ASSET_ROOT / "templates" / "baseline-template.md").read_text(encoding="utf-8")
        text = (
            template.replace("- 主项目：", "- 主项目：demo")
            .replace("- 主项目判断依据：", "- 主项目判断依据：用户指定")
            .replace("- 基线状态：澄清中 / 已确认", "- 基线状态：已确认")
            .replace(
                "- 最终反向确认：待确认 / 已确认（记录用户消息或确认时间）",
                "- 最终反向确认：已确认（用户消息:2026-07-13）",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "00-baseline.md"
            path.write_text(text, encoding="utf-8")

            errors = validate_baseline_doc(path)

        message = "\n".join(errors)
        self.assertIn("缺少实质内容", message)
        self.assertIn("没有真实业务行", message)

    def test_baseline_meta_gate_blocks_deleted_status_fields(self) -> None:
        text = build_confirmed_baseline()
        text = "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith("- 基线状态：") and not line.startswith("- 最终反向确认：")
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "00-baseline.md"
            path.write_text(text, encoding="utf-8")

            errors = validate_baseline_doc(path, clarification_gate_required=True)

        message = "\n".join(errors)
        self.assertIn("缺少强制字段：基线状态", message)
        self.assertIn("缺少强制字段：最终反向确认", message)

    def test_baseline_user_intent_cannot_transfer_downstream(self) -> None:
        text = build_confirmed_baseline().replace(
            "| Q1 | 是否保留历史版本 | 用户意图 | S1 | 口径存在歧义 | 数据身份 | 用户 | 保留历史版本 | 已确认 |",
            "| Q1 | 是否保留历史版本 | 用户意图 | S1 | 口径存在歧义 | 数据身份 | 技术方案 | 交技术方案决定 | 转下游 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "00-baseline.md"
            path.write_text(text, encoding="utf-8")

            errors = validate_baseline_doc(path)

        message = "\n".join(errors)
        self.assertIn("用户意图问题不得转下游", message)
        self.assertIn("用户意图问题必须由用户确认", message)

    def test_baseline_claim_requires_traceable_source(self) -> None:
        text = build_confirmed_baseline().replace(
            "| B2 | 同批试卷和答案题目一致 | 生成请求 | 两个 PDF | 不允许漂移 | 失败可重试 | S1 |",
            "| B2 | 同批试卷和答案题目一致 | 生成请求 | 两个 PDF | 不允许漂移 | 失败可重试 |  |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "00-baseline.md"
            path.write_text(text, encoding="utf-8")

            errors = validate_baseline_doc(path)

        self.assertIn("业务规则B2 缺少准确来源", "\n".join(errors))

    def test_reopen_baseline_resets_confirmation_and_downstream_gates(self) -> None:
        gates = {
            "clarification_required": True,
            "clarification_confirmed": True,
            "alignment_completed": True,
            "design_confirmed": True,
            "tasks_confirmed": True,
            "implementation_completed": True,
            "review_passed": True,
            "test_passed": True,
            "release_ready": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "00-baseline.md"
            path.write_text(build_confirmed_baseline(), encoding="utf-8")

            reopen_baseline_confirmation(path)
            reset_from_baseline(gates)
            reopened = path.read_text(encoding="utf-8")

        self.assertIn("- 基线状态：澄清中", reopened)
        self.assertIn("- 最终反向确认：待确认", reopened)
        self.assertTrue(gates["clarification_required"])
        for key in [
            "clarification_confirmed",
            "alignment_completed",
            "design_confirmed",
            "tasks_confirmed",
            "implementation_completed",
            "review_passed",
            "test_passed",
            "release_ready",
            "business_model_confirmed",
            "upstream_contract_confirmed",
            "schema_confirmed",
        ]:
            self.assertFalse(gates[key])

    def test_sync_clarification_baseline_impact_reopens_persisted_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp)
            gates = {
                "clarification_required": True,
                "clarification_confirmed": True,
                "alignment_completed": True,
                "design_confirmed": True,
                "tasks_confirmed": True,
                "implementation_completed": True,
                "review_passed": True,
                "test_passed": True,
                "release_ready": True,
                "business_model_confirmed": True,
                "upstream_contract_confirmed": True,
            }
            meta = {
                "workflow_schema_version": 4,
                "current_phase": "技术方案",
                "current_status": "已确认",
                "gates": gates,
                "review_flags": {},
            }
            (feature_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (feature_dir / "00-baseline.md").write_text(build_confirmed_baseline(), encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "sync_clarification_impact.py"),
                    "--feature-dir",
                    str(feature_dir),
                    "--impact",
                    "baseline",
                    "--source",
                    "用户消息:2026-07-13",
                    "--summary",
                    "调整生成批次口径",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            updated_meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))
            updated_baseline = (feature_dir / "00-baseline.md").read_text(encoding="utf-8")

        self.assertEqual("待澄清", updated_meta["current_status"])
        self.assertFalse(updated_meta["gates"]["clarification_confirmed"])
        self.assertFalse(updated_meta["gates"]["alignment_completed"])
        self.assertFalse(updated_meta["gates"]["design_confirmed"])
        self.assertTrue(updated_meta["review_flags"]["alignment_needs_review"])
        self.assertTrue(updated_meta["review_flags"]["design_needs_review"])
        self.assertIn("- 基线状态：澄清中", updated_baseline)
        self.assertIn("- 最终反向确认：待确认", updated_baseline)

    def test_confirm_baseline_locks_fingerprint_and_sync_detects_later_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp)
            meta = {
                "workflow_schema_version": 4,
                "current_phase": "需求受理",
                "current_status": "待澄清",
                "gates": {
                    "clarification_required": True,
                    "clarification_confirmed": False,
                },
                "review_flags": {},
                "clarification": {},
            }
            (feature_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            baseline_path = feature_dir / "00-baseline.md"
            baseline_path.write_text(build_confirmed_baseline(), encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "confirm_baseline.py"),
                    "--feature-dir",
                    str(feature_dir),
                    "--source",
                    "用户消息:2026-07-13",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            confirmed_meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertTrue(confirmed_meta["gates"]["clarification_confirmed"])
            self.assertTrue(confirmed_meta["clarification"]["confirmed_baseline_sha256"])

            changed = baseline_path.read_text(encoding="utf-8").replace(
                "生成试卷及答案（来源：S1）",
                "生成两套试卷及答案（来源：S1）",
                1,
            )
            baseline_path.write_text(changed, encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "sync_feature_meta.py"), "--feature-dir", str(feature_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            reopened_meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))
            reopened_baseline = baseline_path.read_text(encoding="utf-8")

        self.assertFalse(reopened_meta["gates"]["clarification_confirmed"])
        self.assertEqual("待澄清", reopened_meta["current_status"])
        self.assertIn("- 基线状态：澄清中", reopened_baseline)
        self.assertIn("- 最终反向确认：待确认", reopened_baseline)

    def test_to_alignment_blocks_unconfirmed_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "init_feature_docs.py"),
                    "--repo-root",
                    str(repo_root),
                    "--feature-name",
                    "未确认需求",
                    "--date",
                    "20260713",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            feature_dir = next((repo_root / "ggg" / "features").iterdir())

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "advance_feature_phase.py"),
                    "--feature-dir",
                    str(feature_dir),
                    "--to-phase",
                    "需求对齐",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("未通过 baseline 门禁", completed.stdout)
        self.assertEqual("需求受理", meta["current_phase"])

    def test_confirmed_current_schema_baseline_can_enter_alignment_with_bundled_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "init_feature_docs.py"),
                    "--repo-root",
                    str(repo_root),
                    "--feature-name",
                    "已确认需求",
                    "--date",
                    "20260713",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            feature_dir = next((repo_root / "ggg" / "features").iterdir())
            (feature_dir / "00-baseline.md").write_text(build_confirmed_baseline(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "confirm_baseline.py"),
                    "--feature-dir",
                    str(feature_dir),
                    "--source",
                    "用户消息:2026-07-13",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "advance_feature_phase.py"),
                    "--feature-dir",
                    str(feature_dir),
                    "--to-phase",
                    "需求对齐",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))
            research = (feature_dir / "01-research.md").read_text(encoding="utf-8")

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertEqual("需求对齐", meta["current_phase"])
        self.assertIn("问题类型", research)
        self.assertFalse((feature_dir / "01-blocking-issues.md").exists())

    def test_schema_v3_baseline_cannot_use_downgraded_meta_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "init", "--repo-root", str(repo_root), "--feature-name", "schema一致性"],
                check=True,
                capture_output=True,
                text=True,
            )
            feature_dir = next((repo_root / "ggg" / "features").iterdir())
            (feature_dir / "00-baseline.md").write_text(build_confirmed_baseline(), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "confirm-baseline", "--feature-dir", str(feature_dir), "--source", "用户确认"],
                check=True,
                capture_output=True,
                text=True,
            )
            meta_path = feature_dir / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["workflow_schema_version"] = 2
            meta["gates"]["clarification_required"] = False
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "to-alignment", "--feature-dir", str(feature_dir)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("两者必须一致", completed.stdout + completed.stderr)

    def test_requirement_research_template_matches_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "requirement-research-template.md").read_text(encoding="utf-8")
        for token in RESEARCH_V2_REQUIRED_TOKENS:
            self.assertIn(token, text)
        self.assertIn("GGG_RESEARCH_SCHEMA_VERSION: 2", text)
        self.assertNotIn("## 8. 代码证据覆盖度", text)
        self.assertIn("唯一的疑问和阻塞问题账本", text)

    def test_requirement_alignment_uses_single_ledger_and_compact_questions(self) -> None:
        skill = skill_path("ggg-requirement-alignment", "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("不创建或维护 `01-blocking-issues.md`", skill)
        self.assertIn("**当前疑问**", skill)
        self.assertIn("**推荐理解**", skill)
        self.assertIn("不能让用户替代码作证", skill)
        self.assertIn("--scope-root <目标项目或模块目录>", skill)
        self.assertIn('codegraph init "<目标项目目录>"', skill)
        self.assertIn('codegraph sync "<目标项目目录>"', skill)
        self.assertIn('codegraph status "<目标项目目录>"', skill)
        self.assertIn("AOP / Aspect", skill)
        self.assertIn("动态 Bean", skill)
        self.assertIn("事务边界", skill)
        self.assertIn("生成代码", skill)
        self.assertIn("共享状态、枚举和类型语义影响矩阵", skill)
        self.assertIn("只搜索枚举类名", skill)
        self.assertIn("需改 / 无需改 / 仅运行验证 / 阻塞", skill)
        self.assertIn("全部 `Bxx` 逐项", skill)
        self.assertIn("不涉及：具体原因", skill)
        self.assertIn("才能作为技术方案的确定依据", skill)
        self.assertNotIn("d:\\towerProject", skill)
        self.assertNotIn("问用户确认后再决定是否记录", skill)

    def test_research_shared_semantic_matrix_accepts_evidence_backed_consumer(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace(
            "- 影响面判断：不涉及：测试样例不新增或修改共享状态、枚举、类型码或字段语义\n"
            "- 检索范围：不涉及",
            "- 影响面判断：涉及\n"
            "- 检索范围：demo-service；TrainingStatus、train_record.status、ReportService 和相关 SQL/XML",
        ).replace(
            "|  |  |  |  |  |  |  |  |  |  |",
            "| 预习状态 | TrainingStatus.PREVIEW / train_record.status=4 | 学习报告 | "
            "ReportService.build | 只统计正式训练 | 预习不计入正式训练报告 | 需改 | E1 | C2 | 无 |",
        ).replace(
            "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 代码已证实 | 高 | 无 | 无 | 影响旧链路 | 无 |",
            "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 代码已证实 | 高 | 无 | 无 | 影响旧链路 | 无 |\n"
            "| C2 | 学习报告读取训练状态并需显式处理预习值 | 共享语义影响 | E1 | "
            "代码已证实 | 高 | 无 | 无 | 预习数据可能进入错误统计 | 无 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path)

        self.assertEqual([], errors)

    def test_research_shared_semantic_matrix_rejects_involved_without_consumers(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace(
            "- 影响面判断：不涉及：测试样例不新增或修改共享状态、枚举、类型码或字段语义\n"
            "- 检索范围：不涉及",
            "- 影响面判断：涉及\n"
            "- 检索范围：demo-service 的 TrainingStatus 和 train_record.status",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path)

        self.assertIn("影响矩阵至少需要一个真实消费场景", "\n".join(errors))

    def test_research_shared_semantic_matrix_requires_specialized_claim(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace(
            "- 影响面判断：不涉及：测试样例不新增或修改共享状态、枚举、类型码或字段语义\n"
            "- 检索范围：不涉及",
            "- 影响面判断：涉及\n"
            "- 检索范围：demo-service 的 TrainingStatus 和 train_record.status",
        ).replace(
            "|  |  |  |  |  |  |  |  |  |  |",
            "| 预习状态 | TrainingStatus.PREVIEW | 错题本 | WrongBookService.collect | "
            "只接收正式训练 | 预习是否进入错题本已确认 | 需改 | E1 | C1 | 无 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path)

        self.assertIn("必须引用类型为“共享语义影响”的 Cxx", "\n".join(errors))

    def test_research_v1_document_remains_compatible(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace("<!-- GGG_RESEARCH_SCHEMA_VERSION: 2 -->\n\n", "")
        shared_section = extract_section(text, "### 6.1 共享状态、枚举和类型语义影响矩阵")
        text = text.replace(shared_section + "\n\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path)

        self.assertEqual([], errors)

    def test_research_question_count_comes_from_single_ledger(self) -> None:
        confirmed = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        )
        pending = confirmed.replace(
            "| Q1 | 主链路是否闭合 | 代码事实 | E1 | 已查证 | 主链路 | 需求对齐 | E1 已证实主链路闭合 | C1 | 已确认 |",
            "| Q1 | 主链路是否闭合 | 代码事实 | E1 | 尚未查清 | 主链路 | 需求对齐 | 继续查证 | C1 | 待确认 |",
        )

        self.assertEqual(0, unresolved_research_questions(confirmed))
        self.assertEqual(1, unresolved_research_questions(pending))

    def test_duplicate_question_ledger_cannot_hide_pending_question(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ) + """

## 9. 进入技术方案前疑问账本

| 编号 | 疑问 | 问题类型 | 准确来源 | 为什么不确定 | 影响范围 | 应由谁确认 | 确认结论/转交说明 | 状态 |
|---|---|---|---|---|---|---|---|---|
| Q2 | 隐藏问题 | 用户意图 | 用户消息 | 尚未确认 | 方案 | 用户 | 待确认 | 待确认 |
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path)

        self.assertIn("必须且只能出现一次", "\n".join(errors))
        self.assertEqual(1, unresolved_research_questions(text))

    def test_sync_meta_uses_research_as_only_question_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "init_feature_docs.py"),
                    "--repo-root",
                    str(repo_root),
                    "--feature-name",
                    "单一疑问账本",
                    "--date",
                    "20260716",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            feature_dir = next((repo_root / "ggg" / "features").iterdir())
            (feature_dir / "00-baseline.md").write_text(build_confirmed_baseline(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "confirm_baseline.py"),
                    "--feature-dir",
                    str(feature_dir),
                    "--source",
                    "用户消息:2026-07-16",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "advance_feature_phase.py"),
                    "--feature-dir",
                    str(feature_dir),
                    "--to-phase",
                    "需求对齐",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            source = repo_root / "src" / "ReportController.java"
            source.parent.mkdir()
            source.write_text("class ReportController {}\n", encoding="utf-8")
            (feature_dir / "01-research.md").write_text(
                build_research_doc("src/ReportController.java:1"),
                encoding="utf-8",
            )
            stale_meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))
            stale_meta["blocking_issue_count"] = 99
            (feature_dir / "meta.json").write_text(
                json.dumps(stale_meta, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "sync_feature_meta.py"), "--feature-dir", str(feature_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))
            legacy_blocker_exists = (feature_dir / "01-blocking-issues.md").exists()
            (feature_dir / "01-blocking-issues.md").write_text("# 旧版阻塞问题\n", encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "sync_feature_meta.py"), "--feature-dir", str(feature_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            legacy_meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))

        self.assertNotIn("blocking_issue_count", meta)
        self.assertEqual("已对齐", meta["current_status"])
        self.assertFalse(legacy_blocker_exists)
        self.assertNotIn("blocking_issue_count", legacy_meta)
        self.assertEqual("待澄清", legacy_meta["current_status"])

    def test_bounded_scanner_rejects_repo_root_without_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            (repo_root / "ggg" / "features").mkdir(parents=True)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "scan-design-inputs",
                    "--scope-root",
                    str(repo_root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("拒绝扫描包含 ggg/features", completed.stdout + completed.stderr)

    def test_bounded_scanner_never_outputs_configuration_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scope = Path(tmp) / "service"
            scope.mkdir()
            (scope / "application.properties").write_text(
                "spring.datasource.url=jdbc:mysql://user:secret@db.internal/demo\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "scan-design-inputs",
                    "--scope-root",
                    str(scope),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertIn("数据源URL", completed.stdout)
        self.assertIn("application.properties", completed.stdout)
        self.assertNotIn("secret", completed.stdout)
        self.assertNotIn("jdbc:mysql", completed.stdout)

    def test_bounded_scanner_max_files_limits_actual_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scope = Path(tmp) / "service"
            source_dir = scope / "src"
            source_dir.mkdir(parents=True)
            for index in range(5):
                (source_dir / f"Demo{index}Controller.java").write_text(
                    f"class Demo{index}Controller {{}}\n",
                    encoding="utf-8",
                )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "scan-design-inputs",
                    "--scope-root",
                    str(scope),
                    "--max-files",
                    "1",
                    "--limit",
                    "20",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertIn("实际纳入文件数：1", completed.stdout)
        self.assertIn("扫描是否因文件上限截断：是", completed.stdout)
        self.assertIn("| src | 1 |", completed.stdout)
        self.assertNotIn("Demo1Controller", completed.stdout)

    def test_bounded_scanner_does_not_follow_symlinks_outside_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = root / "service"
            scope.mkdir()
            outside = root / "Outside.java"
            outside.write_text("@DubboReference class Outside {}\n", encoding="utf-8")
            (scope / "Inside.java").symlink_to(outside)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "scan-design-inputs",
                    "--scope-root",
                    str(scope),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertIn("实际纳入文件数：0", completed.stdout)
        self.assertNotIn("@DubboReference | `Inside.java`", completed.stdout)

    def test_requirement_research_claims_must_reference_existing_evidence(self) -> None:
        research_text = """# 代码调研

## 1. Baseline 验证清单

| baseline 条目 | 需要验证的代码位置 | 验证状态 | 代码事实 | 证据ID | 结论 | 风险 |
|---|---|---|---|---|---|---|
| 主入口 | ReportController | 已验证 | 入口存在 | E1 | 可进入主链路 | 低 |

## 2. 主链路代码事实

- 入口：ReportController.submit
- 数据落点：report_record

## 3. 旧链路副作用清单

| 旧能力 | 代码位置 | 现有语义 | 反向影响范围 | 与本需求关系 | 结论 | 说明 |
|---|---|---|---|---|---|---|
| 报告提交 | ReportService | 写入报告记录 | 提交接口 | 主链路 | 可扩展复用 | 需补状态隔离 |

## 4. 数据身份和状态维度对照

| 业务对象 | 唯一标识 | 去重维度 | 状态隔离维度 | 现有代码/表字段 | 是否满足 | 风险 |
|---|---|---|---|---|---|---|
| 报告 | reportId | reportId | userId + reportId | report_record.report_id | 是 | 低 |

## 5. 复用性分级

| 能力/代码 | 代码位置 | 复用等级 | 原因 | 需要改造点 |
|---|---|---|---|---|
| ReportService | ReportService | 可扩展复用 | 入口一致 | 补隔离字段 |

## 6. 旧能力反向影响检查

| 准备复用/改造的旧能力 | 调用方/影响面 | CodeGraph 证据 | 影响旧场景 | 结论 |
|---|---|---|---|---|
| ReportService.submit | ReportController | E1 | 无新增影响 | 可扩展复用 |

## 7. 跨项目依赖能力

| 项目 | Facade / HTTP / MQ / 表 | 当前能力 | 是否满足本需求 | 缺口 |
|---|---|---|---|---|
| demo-service | report_record | 支持写入 | 是 | 无 |

## 8. 结论账本（Claim Ledger）

| 结论ID | 关键结论 | 结论类型 | 证据ID | 证据等级 | 置信度 | 未覆盖范围 | 运行时证据缺口 | 若结论错误的影响 | 后续确认方式 |
|---|---|---|---|---|---|---|---|---|---|
| C1 | ReportService 可扩展复用 | 复用边界 | E2 | 代码已证实 | 高 | Nacos 开关 | 配置确认 | 影响旧链路 | 配置确认 |

## 9. 进入技术方案前疑问账本

| 编号 | 疑问 | 问题类型 | 准确来源 | 为什么不确定 | 影响范围 | 应由谁确认 | 确认结论/转交说明 | 状态 |
|---|---|---|---|---|---|---|---|---|
| Q1 | 主链路是否闭合 | 代码事实 | E1 | 已查证 | 主链路 | 需求对齐 | E1 已证实主链路闭合 | 已确认 |

## 10. 残余风险和后续确认方式

- 已确认：主链路已覆盖。
- 未覆盖：Nacos 开关待配置确认。

## 11. 代码证据索引

| 编号 | 项目 | 类型 | 位置 | 结论说明 |
|---|---|---|---|---|
| E1 | demo-service | Controller | ReportController.java:18 | 主入口 |
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(research_text, encoding="utf-8")

            errors = validate_research_doc(path)

        self.assertIn("01-research.md C1 引用了不存在于代码证据索引的证据ID: E2", "\n".join(errors))

    def test_research_blocking_signals_cannot_pass_validation(self) -> None:
        base = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        )
        variants = {
            "Baseline": base.replace(
                "| B1 | 用户路径 | ReportController | 已验证 | 入口存在 | E1 | 可进入主链路 | C1 | 无 |",
                "| B1 | 用户路径 | ReportController | 阻塞 | 入口未闭合 | E1 | Q1 待查 | C1 | Q1 影响方案 |",
            ),
            "Claim": base.replace(
                "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 代码已证实 | 高 | 无 | 无 | 影响旧链路 | 无 |",
                "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 阻塞 | 低 | Q1 尚未闭合 | 无 | 影响旧链路 | 继续查 Q1 |",
            ),
            "残余": base.replace("- 阻塞风险：无", "- 阻塞风险：Q1 尚未闭合"),
            "重复残余": base.replace("- 阻塞风险：无", "- 阻塞风险：无\n- 阻塞风险：Q1 尚未闭合"),
            "Baseline状态伪装": base.replace(
                "| B1 | 用户路径 | ReportController | 已验证 | 入口存在 | E1 | 可进入主链路 | C1 | 无 |",
                "| B1 | 用户路径 | ReportController | 部分验证 | 入口存在 | E1 | Q1 待查 | C1 | Q1 阻塞方案 |",
            ),
            "Claim等级伪装": base.replace(
                "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 代码已证实 | 高 | 无 | 无 | 影响旧链路 | 无 |",
                "| C1 | Q1 未闭合，阻塞方案 | 复用边界 | E1 | 代码已证实 | 中 | 无 | 无 | 影响旧链路 | 继续确认 |",
            ),
        }
        for label, text in variants.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "01-research.md"
                path.write_text(text, encoding="utf-8")
                errors = validate_research_doc(path)
                self.assertIn("不能完成需求对齐", "\n".join(errors))

    def test_research_explicit_non_blocking_gaps_can_pass_validation(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace(
            "| B1 | 用户路径 | ReportController | 已验证 | 入口存在 | E1 | 可进入主链路 | C1 | 无 |",
            "| B1 | 用户路径 | ReportController | 部分验证 | 入口存在 | E1 | 可进入主链路 | C1 | 非阻塞配置缺口 |",
        ).replace(
            "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 代码已证实 | 高 | 无 | 无 | 影响旧链路 | 无 |",
            "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 推断 | 中 | 不会阻塞方案的配置缺口 | 配置确认 | 影响旧链路 | 上线前配置确认 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path)

        self.assertEqual([], errors)

    def test_schema_v4_research_must_cover_every_baseline_item(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace(
            "| B5 | 验收标准 | ReportController | 已验证 | 入口可验证 | E1 | 验收链路已闭合 | C1 | 无 |\n",
            "",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path, baseline_text=build_confirmed_baseline())

        self.assertIn("遗漏基线条目: B5", "\n".join(errors))

    def test_schema_v4_research_rejects_empty_main_flow_and_template_rows(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace(
            "- 核心处理与异步链路：ReportService.submit，同步处理",
            "- 核心处理与异步链路：",
        ).replace(
            "| ReportService | ReportService | 可扩展复用 | 入口一致 | 补隔离字段 | C1 |",
            "|  |  | 可直接复用 / 可扩展复用 / 只可参考 / 禁止复用 / 必须新增 |  |  | C1 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path, baseline_text=build_confirmed_baseline())

        message = "\n".join(errors)
        self.assertIn("主链路代码事实缺少实质内容", message)
        self.assertIn("复用性分级没有真实业务行", message)

    def test_schema_v4_research_rejects_uncovered_status_disguised_as_proven(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace(
            "| B1 | 用户路径 | ReportController | 已验证 | 入口存在 | E1 | 可进入主链路 | C1 | 无 |",
            "| B1 | 用户路径 | ReportController | 未覆盖 | 当前证据未覆盖 | E1 | 尚未闭合 | C1 | 影响入口判断 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path, baseline_text=build_confirmed_baseline())

        self.assertIn("为未覆盖，但 C1 被写成已证实结论", "\n".join(errors))

    def test_research_rejects_empty_uncertainty_and_duplicate_ids(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        ).replace(
            "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 代码已证实 | 高 | 无 | 无 | 影响旧链路 | 无 |",
            "| C1 | ReportService 可扩展复用 | 复用边界 | E1 | 未覆盖 | 低 | 无 | 无 | 影响旧链路 | 无 |\n"
            "| C1 | ReportService 禁止复用 | 复用边界 | E1 | 代码已证实 | 高 | 无 | 无 | 影响旧链路 | 无 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_research_doc(path)

        message = "\n".join(errors)
        self.assertIn("结论编号重复: C1", message)
        self.assertIn("必须写清未覆盖范围和后续确认方式", message)

    def test_technical_design_rejects_unclosed_claim_as_authoritative_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            path.write_text(build_design_doc("C1"), encoding="utf-8")
            errors = validate_design_doc(
                path,
                valid_claim_ids={"C1"},
                eligible_claim_ids=set(),
            )

        self.assertIn("不能作为确定方案依据的结论ID: C1", "\n".join(errors))

    def test_technical_design_rejects_blank_contract_and_identity_confirmation_only(self) -> None:
        text = build_design_doc("C1").replace(
            "| 报告 | reportId | userId + reportId | reportId | 创建到完成 | C1 | 是 |",
            "| 报告 |  |  |  |  | C1 | 是 |",
        ).replace(
            "| 提交 | submit | 提交后 | reportId | userId | userId | 结果 | C1 | 提交报告 |",
            "| 提交 |  |  |  |  |  |  | C1 |  |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_design_doc(path, valid_claim_ids={"C1"}, eligible_claim_ids={"C1"})

        message = "\n".join(errors)
        self.assertIn("实例身份表行“报告”缺少实质字段: 唯一标识", message)
        self.assertIn("前后端接口协作流行“提交”缺少实质字段: 调用接口", message)

    def test_technical_design_research_inputs_must_be_fully_covered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            path.write_text(build_design_doc("C1"), encoding="utf-8")
            errors = validate_design_doc(
                path,
                valid_claim_ids={"C1", "C2"},
                eligible_claim_ids={"C1", "C2"},
                transferred_question_ids={"Q2"},
            )

        message = "\n".join(errors)
        self.assertIn("遗漏 Research 输入: C2", message)
        self.assertIn("遗漏 Research 输入: Q2", message)

    def test_technical_design_selected_mq_requires_substantive_detail(self) -> None:
        text = build_design_doc("C1").replace(
            "| 报告记录 | MySQL | 是 | 否 | 否 | 否 | 否 | 长期业务事实 | 事务提交 | C1 |",
            "| 报告记录 | MySQL + MQ | 是 | 否 | 否 | 是 | 否 | 长期业务事实 | 事务与事件最终一致 | C1 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_design_doc(path, valid_claim_ids={"C1"}, eligible_claim_ids={"C1"})

        self.assertIn("选择了 MQ，但缺少对应非 MySQL 承载明细", "\n".join(errors))

    def test_technical_design_requires_minimal_solution_evidence(self) -> None:
        text = build_design_doc("C1").replace(
            "现有 ReportService 已承载提交主链路",
            "",
        ).replace(
            "当前单体事务可满足一致性且新增组件只会增加维护成本",
            "方便扩展",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_design_doc(path, valid_claim_ids={"C1"}, eligible_claim_ids={"C1"})

        message = "\n".join(errors)
        self.assertIn("最小方案与复杂度准入行“报告提交”缺少实质字段: 当前能力/可复用落点", message)
        self.assertIn("字段 不采用复杂方案原因 过于空泛: 方便扩展", message)

    def test_technical_design_mysql_change_requires_sql_admission_evidence(self) -> None:
        text = build_design_doc("C1").replace(
            "- MySQL 结构变更：无",
            "- MySQL 结构变更：有",
        ).replace(
            "现有表已承载报告事实，只需补齐报告标识约束",
            "",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_design_doc(path, valid_claim_ids={"C1"}, eligible_claim_ids={"C1"})

        self.assertIn("SQL 表准入行“report_record”缺少实质字段: 现有承载评估", "\n".join(errors))

    def test_technical_design_decision_ledger_rejects_duplicate_and_undefined_ids(self) -> None:
        text = build_design_doc("C1").replace(
            "| D1 | 提交链路 | ReportService 已承载提交且事务边界清晰 | 复用 ReportService 并修改旧表 | 新增 Service、独立表和 MQ | 当前链路可满足同步提交，引入额外组件会增加一致性成本 | C1 | 修改范围小，但需验证旧表兼容 | 跨系统异步处理成为已确认要求时升级 | 编译、接口测试和数据唯一性验证 |",
            "| D1 | 提交链路 | ReportService 已承载提交且事务边界清晰 | 复用 ReportService 并修改旧表 | 新增 Service、独立表和 MQ | 当前链路可满足同步提交，引入额外组件会增加一致性成本 | C1 | 修改范围小，但需验证旧表兼容 | 跨系统异步处理成为已确认要求时升级 | 编译、接口测试和数据唯一性验证 |\n"
            "| D1 | 数据承载 | 旧表生命周期与记录一致 | 复用旧表 | 新建独立表 | 新表不会增加业务表达能力 | C1 | 少一次表维护 | 旧表无法安全承载时升级 | 表结构与查询验证 |",
        ).replace(
            "| D1 | demo | Service | ReportService | 修改 | C1 | 提交 |",
            "| D2 | demo | Service | ReportService | 修改 | C1 | 提交 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            path.write_text(text, encoding="utf-8")
            errors = validate_design_doc(path, valid_claim_ids={"C1"}, eligible_claim_ids={"C1"})

        message = "\n".join(errors)
        self.assertIn("设计决策记录编号重复: D1", message)
        self.assertIn("未在设计决策记录中定义的设计ID: D2", message)

    def test_interface_total_and_detail_must_close_one_to_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            details = root / "interface-details"
            details.mkdir()
            design.write_text(build_design_doc("C1"), encoding="utf-8")
            missing_errors = validate_design_doc(design, details, {"C1"}, {"C1"}, set())
            (details / "02-interface-01-submit.md").write_text(
                build_interface_detail("D1", "C9"), encoding="utf-8"
            )
            mismatch_errors = validate_design_doc(
                design, details, {"C1", "C9"}, {"C1", "C9"}, set()
            )

        self.assertIn("接口总表引用的明细文档不存在", "\n".join(missing_errors))
        self.assertIn("来源Cxx与接口总表不一致", "\n".join(mismatch_errors))

    def test_schema_rejects_minimal_sql_and_accepts_substantive_ddl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "04-schema.sql"
            path.write_text("CREATE TABLE x(id int);\n", encoding="utf-8")
            minimal_errors = validate_schema_doc(path, {}, {"C1"}, {"D1"})
            path.write_text(build_schema_sql(), encoding="utf-8")
            valid_errors = validate_schema_doc(path, {}, {"C1"}, {"D1"})

        self.assertIn("缺少实质元数据: 变更目标", "\n".join(minimal_errors))
        self.assertIn("缺少主键", "\n".join(minimal_errors))
        self.assertEqual([], valid_errors)

    def test_schema_v2_rejects_vague_evidence_and_duplicate_index(self) -> None:
        text = build_schema_sql().replace(
            "-- 核心查询: 按 report_id 等值查询单条记录",
            "-- 核心查询: 支持查询",
        ).replace(
            "  UNIQUE KEY `uk_report_id` (`report_id`)",
            "  UNIQUE KEY `uk_report_id` (`report_id`),\n  KEY `idx_report_id` (`report_id`)",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "04-schema.sql"
            path.write_text(text, encoding="utf-8")
            errors = validate_schema_doc(path, {}, {"C1"}, {"D1"})

        message = "\n".join(errors)
        self.assertIn("元数据过于空泛: 核心查询=支持查询", message)
        self.assertIn("存在重复索引列组合: uk_report_id 与 idx_report_id", message)

    def test_design_v5_and_sql_v3_close_per_ddl_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            schema = root / "04-schema.sql"
            design.write_text(
                build_design_doc_v5(
                    mysql_change=True,
                    detail_value="无需：简单内部调用不需要独立明细",
                ),
                encoding="utf-8",
            )
            schema.write_text(build_schema_sql_v3(), encoding="utf-8")
            design_errors = validate_design_doc(
                design,
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )
            schema_errors = validate_schema_doc(schema, {}, {"C1"}, {"D1"})

        self.assertEqual([], design_errors)
        self.assertEqual([], schema_errors)

    def test_sql_v3_create_quality_ignores_semicolons_inside_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "04-schema.sql"
            path.write_text(build_schema_sql_v3(comment_with_semicolon=True), encoding="utf-8")
            errors = validate_schema_doc(path, {}, {"C1"}, {"D1"})

        self.assertEqual([], errors)

    def test_design_v5_and_sql_v3_close_multiple_objects_bidirectionally(self) -> None:
        design_text = build_design_doc_v5(
            mysql_change=True,
            detail_value="无需：简单内部调用不需要独立明细",
        )
        base_row = (
            "| D1 | report_record | create | id, report_id, PRIMARY KEY, uk_report_id | 普通 | "
            "新建隔离空表，无存量数据和锁表风险 | 持久化报告唯一事实 | "
            "现有表语义不同，新建隔离对象 | 提交写入并按 report_id 查询 | "
            "report_id 业务唯一 | 先建表再发布；回滚删除新表；SHOW CREATE TABLE 验证 | C1 |"
        )
        second_row = (
            "| D1 | audit_record | create | id, PRIMARY KEY | 普通 | "
            "新建审计空表，无存量数据 | 记录报告提交审计事实 | "
            "现有对象不承载审计语义 | 提交成功后写入并按 id 查询 | "
            "主键满足单条查询 | 先建表再发布；回滚删除新表；SHOW CREATE TABLE 验证 | C1 |"
        )
        design_text = design_text.replace(base_row, f"{base_row}\n{second_row}")
        second_marker = json.dumps(
            {
                "object": "audit_record",
                "operation": "create",
                "members": ["id", "PRIMARY KEY"],
                "risk": "普通",
                "risk_reason": "新建审计空表，无存量数据",
                "claims": ["C1"],
                "designs": ["D1"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        schema_text = build_schema_sql_v3() + f"""
-- GGG_DDL_OBJECT: {second_marker}
CREATE TABLE `audit_record` (
  `id` bigint NOT NULL COMMENT '主键',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审计记录';
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            design.write_text(design_text, encoding="utf-8")
            (root / "04-schema.sql").write_text(schema_text, encoding="utf-8")
            errors = validate_design_doc(
                design,
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )

        self.assertEqual([], errors)

    def test_sql_v3_closure_rejects_missing_extra_member_risk_reason_and_claim_drift(self) -> None:
        extra_marker = json.dumps(
            {
                "object": "audit_record",
                "operation": "create",
                "members": ["id", "PRIMARY KEY"],
                "risk": "普通",
                "risk_reason": "新建审计空表，无存量数据",
                "claims": ["C1"],
                "designs": ["D1"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        extra_sql = f"""
-- GGG_DDL_OBJECT: {extra_marker}
CREATE TABLE `audit_record` (
  `id` bigint NOT NULL COMMENT '主键',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审计记录';
"""
        scenarios = [
            (
                "missing",
                build_design_doc_v5(
                    mysql_change=True,
                    detail_value="无需：简单内部调用不需要独立明细",
                    ddl_object="missing_record",
                ),
                build_schema_sql_v3(),
                "未在 04-schema.sql 闭环",
            ),
            (
                "extra",
                build_design_doc_v5(
                    mysql_change=True,
                    detail_value="无需：简单内部调用不需要独立明细",
                ),
                build_schema_sql_v3() + extra_sql,
                "未在 02-design.md 闭环",
            ),
            (
                "member",
                build_design_doc_v5(
                    mysql_change=True,
                    detail_value="无需：简单内部调用不需要独立明细",
                    ddl_members="id, report_id, PRIMARY KEY, idx_report_id",
                ),
                build_schema_sql_v3(),
                "DDL对象覆盖",
            ),
            (
                "risk",
                build_design_doc_v5(
                    mysql_change=True,
                    detail_value="无需：简单内部调用不需要独立明细",
                    ddl_risk="高风险",
                ),
                build_schema_sql_v3(),
                "风险等级",
            ),
            (
                "risk_reason",
                build_design_doc_v5(
                    mysql_change=True,
                    detail_value="无需：简单内部调用不需要独立明细",
                    ddl_risk_reason="接口发布前执行并观察业务日志",
                ),
                build_schema_sql_v3(),
                "风险依据/执行条件",
            ),
            (
                "claim",
                build_design_doc_v5(
                    mysql_change=True,
                    detail_value="无需：简单内部调用不需要独立明细",
                ),
                build_schema_sql_v3(source_claim="C2"),
                "来源Cxx",
            ),
        ]
        for name, design_text, schema_text, expected in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                design = root / "02-design.md"
                design.write_text(design_text, encoding="utf-8")
                (root / "04-schema.sql").write_text(schema_text, encoding="utf-8")
                errors = validate_design_doc(
                    design,
                    valid_claim_ids={"C1", "C2"},
                    eligible_claim_ids={"C1"},
                    transferred_question_ids=set(),
                )
                self.assertIn(expected, "\n".join(errors))

    def test_sql_v3_alter_members_cover_index_constraint_and_rename_targets(self) -> None:
        statements = [
            ("DROP INDEX `idx_old`", ["idx_old"]),
            ("RENAME INDEX `idx_old` TO `idx_new`", ["idx_old", "idx_new"]),
            ("DROP PRIMARY KEY", ["PRIMARY KEY"]),
            ("DROP FOREIGN KEY `fk_owner`", ["fk_owner"]),
            ("RENAME COLUMN `old_name` TO `new_name`", ["old_name", "new_name"]),
        ]
        chunks = []
        for clause, members in statements:
            marker = json.dumps(
                {
                    "object": "report_record",
                    "operation": "alter",
                    "members": members,
                    "risk": "高风险",
                    "risk_reason": "修改存量表结构并持有元数据锁",
                    "claims": ["C1"],
                    "designs": ["D1"],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            chunks.append(f"-- GGG_DDL_OBJECT: {marker}\nALTER TABLE `report_record` {clause};")
        errors: list[str] = []
        entries = extract_sql_v3_ddl_entries("\n".join(chunks), errors)

        self.assertEqual([], errors)
        self.assertEqual([set(members) for _clause, members in statements], [entry["members"] for entry in entries])

    def test_sql_v3_rejects_multi_object_drop_and_rename_statements(self) -> None:
        chunks = []
        for statement, ddl_object in [
            ("DROP TABLE `report_a`, `report_b`;", "report_a"),
            ("RENAME TABLE `report_a` TO `report_b`, `report_c` TO `report_d`;", "report_a->report_b"),
        ]:
            marker = json.dumps(
                {
                    "object": ddl_object,
                    "operation": "drop" if statement.startswith("DROP") else "rename",
                    "members": ["*"],
                    "risk": "高风险",
                    "risk_reason": "删除或重命名存量对象会中断旧读写",
                    "claims": ["C1"],
                    "designs": ["D1"],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            chunks.append(f"-- GGG_DDL_OBJECT: {marker}\n{statement}")
        errors: list[str] = []
        extract_sql_v3_ddl_entries("\n".join(chunks), errors)

        self.assertEqual(2, sum("多对象必须拆成独立 DDL" in error for error in errors))

    def test_sql_v3_rejects_marker_target_drift_and_understated_syntax_risk(self) -> None:
        wrong_target = json.dumps(
            {
                "object": "other_record",
                "operation": "create",
                "members": ["id", "PRIMARY KEY"],
                "risk": "普通",
                "risk_reason": "新建隔离空表，无存量数据",
                "claims": ["C1"],
                "designs": ["D1"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        understated_risk = json.dumps(
            {
                "object": "report_record",
                "operation": "alter",
                "members": ["report_id"],
                "risk": "普通",
                "risk_reason": "已安排低峰期执行并观察锁等待",
                "claims": ["C1"],
                "designs": ["D1"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        text = f"""-- GGG_DDL_OBJECT: {wrong_target}
CREATE TABLE `report_record` (
  `id` bigint NOT NULL COMMENT '主键',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报告记录';
-- GGG_DDL_OBJECT: {understated_risk}
ALTER TABLE `report_record` MODIFY COLUMN `report_id` bigint NOT NULL;
"""
        errors: list[str] = []
        extract_sql_v3_ddl_entries(text, errors)
        message = "\n".join(errors)

        self.assertIn("object=other_record 与真实对象 report_record 不一致", message)
        self.assertIn("语法风险下限为高风险，不能声明普通", message)

    def test_design_v5_precheck_uses_risk_to_lock_only_high_risk_downstream_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            details = root / "interface-details"
            details.mkdir()
            (details / "02-interface-01-submit.md").write_text(
                build_interface_detail_v3(),
                encoding="utf-8",
            )
            design.write_text(
                build_design_doc_v5(mysql_change=True, state="SQL待确认"),
                encoding="utf-8",
            )
            (root / "04-schema.sql").write_text(build_schema_sql_v3(), encoding="utf-8")
            ordinary_errors = validate_design_precheck(design, {"C1"}, set())

            design.write_text(
                build_design_doc_v5(
                    mysql_change=True,
                    state="SQL待确认",
                    ddl_operation="alter",
                    ddl_members="report_id",
                    ddl_risk="高风险",
                    ddl_risk_reason="修改非空列定义会重建存量表并持有元数据锁",
                ),
                encoding="utf-8",
            )
            (root / "04-schema.sql").write_text(build_high_risk_schema_sql_v3(), encoding="utf-8")
            high_risk_errors = validate_design_precheck(design, {"C1"}, set())

        self.assertEqual([], ordinary_errors)
        high_risk_message = "\n".join(high_risk_errors)
        self.assertIn("高风险 DDL 确认前不得填写依赖章节", high_risk_message)
        self.assertIn("高风险 DDL 确认前不得创建 interface-details/", high_risk_message)

    def test_design_v5_precheck_before_schema_validates_only_sections_zero_to_four(self) -> None:
        text = build_design_doc_v5(mysql_change=True, state="SQL待确认")
        sql_section = extract_section(text, "## 五、SQL 变更说明")
        text = text.replace(sql_section, "## 五、SQL 变更说明", 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            details = root / "interface-details"
            details.mkdir()
            (details / "02-interface-01-submit.md").write_text(
                build_interface_detail_v3(),
                encoding="utf-8",
            )
            design.write_text(text, encoding="utf-8")
            errors = validate_design_precheck(design, {"C1"}, set())

        self.assertEqual([], errors)

    def test_design_v4_and_sql_v2_remain_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / "02-design.md"
            schema = root / "04-schema.sql"
            design.write_text(
                build_design_doc_v4(mysql_change=True),
                encoding="utf-8",
            )
            schema.write_text(build_schema_sql(), encoding="utf-8")
            design_errors = validate_design_doc(
                design,
                root / "interface-details",
                valid_claim_ids={"C1"},
                eligible_claim_ids={"C1"},
                transferred_question_ids=set(),
            )
            schema_errors = validate_schema_doc(schema, {}, {"C1"}, {"D1"})

        self.assertEqual([], design_errors)
        self.assertEqual([], schema_errors)

    def test_confirm_schema_locks_fingerprint_and_sql_change_invalidates_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp)
            meta = {
                "workflow_schema_version": 4,
                "feature_name": "SQL确认",
                "current_phase": "技术方案",
                "current_status": "方案中",
                "gates": {"schema_confirmed": False},
                "review_flags": {},
            }
            (feature_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            (feature_dir / "01-research.md").write_text(build_research_doc("接口验证记录"), encoding="utf-8")
            precheck = build_design_precheck("C1")
            (feature_dir / "02-design.md").write_text(precheck, encoding="utf-8")
            schema_path = feature_dir / "04-schema.sql"
            schema_path.write_text(build_schema_sql(), encoding="utf-8")

            blank_source = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "confirm-schema", "--feature-dir", str(feature_dir), "--source", "   "],
                check=False,
                capture_output=True,
                text=True,
            )
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "confirm-schema", "--feature-dir", str(feature_dir), "--source", "用户消息 2026-07-16"],
                check=False,
                capture_output=True,
                text=True,
            )
            locked_meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))
            schema_path.write_text(build_schema_sql().replace("报告记录表", "报告记录主表"), encoding="utf-8")
            validation_errors = validate_feature_dir(feature_dir)

        self.assertNotEqual(0, blank_source.returncode)
        self.assertIn("不能只包含空白", blank_source.stdout + blank_source.stderr)
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertTrue(locked_meta["gates"]["schema_confirmed"])
        self.assertEqual("用户消息 2026-07-16", locked_meta["schema_confirmation"]["confirmation_source"])
        self.assertIn("04-schema.sql 在用户确认后发生变化", "\n".join(validation_errors))

    def test_schema_precheck_rejects_early_full_design_and_interface_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "02-design.md"
            early_full_design = build_design_doc("C1").replace("- 设计状态：已完成", "- 设计状态：SQL待确认").replace(
                "- MySQL 结构变更：无", "- MySQL 结构变更：有"
            )
            path.write_text(early_full_design, encoding="utf-8")
            details = root / "interface-details"
            details.mkdir()
            (details / "02-interface-01-submit.md").write_text(build_interface_detail(), encoding="utf-8")
            errors = validate_design_precheck(path, {"C1"}, set())

        message = "\n".join(errors)
        self.assertIn("SQL 确认前不得填写锁定章节", message)
        self.assertIn("SQL 确认前不得创建 interface-details/", message)

    def test_to_design_creates_schema_only_after_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            feature_dir = repo_root / "ggg" / "features" / "20260716-schema"
            (repo_root / "ggg" / "workflow" / "templates").mkdir(parents=True)
            feature_dir.mkdir(parents=True)
            meta = {
                "workflow_schema_version": 4,
                "feature_name": "SQL预检",
                "current_phase": "技术方案",
                "current_status": "方案中",
                "gates": {"schema_confirmed": False},
                "review_flags": {"alignment_needs_review": False, "design_needs_review": False, "tasks_needs_review": False},
            }
            (feature_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            (feature_dir / "01-research.md").write_text(build_research_doc("接口验证记录"), encoding="utf-8")
            (feature_dir / "02-design.md").write_text(build_design_precheck(), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "to-design",
                    "--feature-dir",
                    str(feature_dir),
                    "--create-schema",
                    "--business-model-confirmed",
                    "--upstream-contract-confirmed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            schema_text = (feature_dir / "04-schema.sql").read_text(encoding="utf-8") if (feature_dir / "04-schema.sql").exists() else ""
            updated_meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("-- 来源Cxx:", schema_text)
        self.assertFalse(updated_meta["gates"]["schema_confirmed"])

    def test_to_design_rejects_residual_blocker_even_when_q_ledger_is_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "init", "--repo-root", str(repo_root), "--feature-name", "阻塞门禁"],
                check=True,
                capture_output=True,
                text=True,
            )
            feature_dir = next((repo_root / "ggg" / "features").iterdir())
            (feature_dir / "00-baseline.md").write_text(build_confirmed_baseline(), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "confirm-baseline", "--feature-dir", str(feature_dir), "--source", "用户确认"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "to-alignment", "--feature-dir", str(feature_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            source = repo_root / "src" / "ReportController.java"
            source.parent.mkdir()
            source.write_text("class ReportController {}\n", encoding="utf-8")
            research = build_research_doc("src/ReportController.java:1").replace(
                "- 阻塞风险：无",
                "- 阻塞风险：无\n- 阻塞风险：Q1 仍影响方案",
            )
            (feature_dir / "01-research.md").write_text(research, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "workflow_cli.py"), "to-design", "--feature-dir", str(feature_dir)],
                check=False,
                capture_output=True,
                text=True,
            )
            design_created = (feature_dir / "02-design.md").exists()

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("仍存在残余阻塞风险", completed.stdout + completed.stderr)
        self.assertFalse(design_created)

    def test_requirement_research_user_intent_cannot_transfer_downstream(self) -> None:
        text = build_research_doc("接口验证记录").replace(
            "| E1 | demo-service | Controller | 接口验证记录 | 主入口 |",
            "| E1 | demo-service | 接口 | 接口验证记录 | 主入口 |",
        )
        text = text.replace(
            "| Q1 | 主链路是否闭合 | 代码事实 | E1 | 已查证 | 主链路 | 需求对齐 | E1 已证实主链路闭合 | C1 | 已确认 |",
            "| Q1 | 是否允许覆盖旧批次 | 用户意图 | 用户消息:2026-07-13 | 口径冲突 | 数据身份 | 技术方案 | 交技术方案决定 | C1 | 转下游 |",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(text, encoding="utf-8")

            errors = validate_research_doc(path)

        self.assertIn("用户意图问题必须由用户确认，不得转下游", "\n".join(errors))

    def test_requirement_research_file_evidence_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            feature_dir = repo_root / "ggg" / "features" / "20260701-demo"
            feature_dir.mkdir(parents=True)
            path = feature_dir / "01-research.md"
            path.write_text(
                build_research_doc("src/main/java/demo/MissingController.java:2"),
                encoding="utf-8",
            )

            errors = validate_research_doc(path, repo_root)

        self.assertIn(
            "01-research.md E1 证据位置文件不存在: src/main/java/demo/MissingController.java",
            "\n".join(errors),
        )

    def test_requirement_research_file_evidence_accepts_existing_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            source = repo_root / "src" / "main" / "java" / "demo" / "ReportController.java"
            source.parent.mkdir(parents=True)
            source.write_text(
                "package demo;\npublic class ReportController {\n    void submit() {}\n}\n",
                encoding="utf-8",
            )
            feature_dir = repo_root / "ggg" / "features" / "20260701-demo"
            feature_dir.mkdir(parents=True)
            path = feature_dir / "01-research.md"
            path.write_text(
                build_research_doc("src/main/java/demo/ReportController.java:2"),
                encoding="utf-8",
            )

            errors = validate_research_doc(path, repo_root)

        self.assertEqual([], errors)

    def test_technical_design_claim_refs_must_exist_in_research(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            path.write_text(build_design_doc("C9"), encoding="utf-8")

            errors = validate_design_doc(path, valid_claim_ids={"C1"})

        self.assertIn(
            "02-design.md 引用了 01-research.md 中不存在的结论ID: C9",
            "\n".join(errors),
        )

    def test_technical_design_traceable_rows_each_need_claim_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "02-design.md"
            text = build_design_doc("C1").replace(
                "| D1 | demo | Service | ReportService | 修改 | C1 | 提交 |",
                "| D1 | demo | Service | ReportService | 修改 | - | 提交 |",
            )
            path.write_text(text, encoding="utf-8")

            errors = validate_design_doc(path, valid_claim_ids={"C1"})

        self.assertIn("02-design.md 的 ## 六、核心改动 行“D1”缺少 Cxx 来源引用", "\n".join(errors))

    def test_task_breakdown_requires_traceable_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(build_tasks_doc("-"), encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        self.assertIn("03-tasks.md T1 缺少来源依据", "\n".join(errors))

    def test_task_breakdown_detail_requires_traceable_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            text = build_tasks_doc("D1 / C1")
            text = text.replace(
                "- 来源依据：D1 / C1\n- 所属项目：demo",
                "- 来源依据：\n- 所属项目：demo",
                1,
            )
            path.write_text(text, encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        error_text = "\n".join(errors)
        self.assertIn("03-tasks.md T1 任务详情 缺少来源依据", error_text)
        self.assertIn("03-tasks.md T1 的来源依据在任务总览和详情中不一致", error_text)

    def test_task_breakdown_source_refs_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(build_tasks_doc("D9 / C9"), encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        error_text = "\n".join(errors)
        self.assertIn("03-tasks.md T1 引用了 02-design.md 中不存在的设计ID: D9", error_text)
        self.assertIn("03-tasks.md T1 引用了 01-research.md 中不存在的结论ID: C9", error_text)

    def test_task_breakdown_requires_core_design_source_not_claim_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(build_tasks_doc("C1"), encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        self.assertIn(
            "03-tasks.md T1 来源依据必须引用至少一个核心改动 Dxx",
            "\n".join(errors),
        )

    def test_task_breakdown_must_cover_every_core_change_design_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks_path = root / "03-tasks.md"
            design_path = root / "02-design.md"
            tasks_path.write_text(build_tasks_doc("D1 / C1"), encoding="utf-8")
            design_path.write_text(
                """# 技术方案

## 六、核心改动

| 设计ID | 项目 | 类型 | 类/文件/表 | 改动类型 | 来源Cxx | 改动说明 |
|---|---|---|---|---|---|---|
| D1 | demo | Service | ReportService | 修改 | C1 | 提交报告 |
| D2 | demo | Controller | ReportController | 修改 | C1 | 提交入口 |
""",
                encoding="utf-8",
            )

            errors = validate_tasks_doc(
                tasks_path,
                valid_design_ids={"D1", "D2"},
                valid_claim_ids={"C1"},
            )

        self.assertIn("03-tasks.md 遗漏 02-design.md 核心改动: D2", "\n".join(errors))

    def test_task_breakdown_valid_code_tasks_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(build_tasks_doc(), encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        self.assertEqual([], errors)

    def test_task_breakdown_rejects_duplicate_and_missing_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            text = build_tasks_doc().replace(
                "| T1 | 实现报告提交服务 | D1 / C1 | demo | src/main/java/demo/ReportService.java | - |",
                "| T1 | 实现报告提交服务 | D1 / C1 | demo | src/main/java/demo/ReportService.java | T99 |",
                1,
            ).replace(
                "- 依赖任务：-",
                "- 依赖任务：T99",
                1,
            )
            task_row = "| T1 | 实现报告提交服务 | D1 / C1 | demo | src/main/java/demo/ReportService.java | T99 | ReportService 按 reportId 保存报告且重复提交返回既有结果 |"
            text = text.replace(task_row, f"{task_row}\n{task_row}")
            path.write_text(text, encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        error_text = "\n".join(errors)
        self.assertIn("03-tasks.md 编码任务编号重复: T1", error_text)
        self.assertIn("03-tasks.md T1 依赖不存在的任务: T99", error_text)

    def test_task_breakdown_rejects_dependency_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            text = build_tasks_doc().replace(
                "- 推荐执行顺序：T1",
                "- 推荐执行顺序：T1 -> T2",
            ).replace(
                "| T1 | 实现报告提交服务 | D1 / C1 | demo | src/main/java/demo/ReportService.java | - |",
                "| T1 | 实现报告提交服务 | D1 / C1 | demo | src/main/java/demo/ReportService.java | T2 |",
            ).replace(
                "- 依赖任务：-",
                "- 依赖任务：T2",
                1,
            )
            task2_row = "| T2 | 实现报告读取服务 | D1 / C1 | demo | src/main/java/demo/ReportQueryService.java | T1 | ReportQueryService 按 reportId 返回已保存报告 |"
            text = text.replace(
                "## 4. 任务详情",
                f"{task2_row}\n\n## 4. 任务详情",
            ).replace(
                "## 5. 完成定义",
                """### T2 实现报告读取服务

- 来源依据：D1 / C1
- 所属项目：demo
- 依赖任务：T1
- 预计修改文件/符号：src/main/java/demo/ReportQueryService.java
- 主要实现内容：
  - 按 reportId 查询报告。
- 代码边界：
  - 不修改提交逻辑。
- 完成标准：
  - ReportQueryService 按 reportId 返回已保存报告。

## 5. 完成定义""",
            )
            path.write_text(text, encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        self.assertIn("03-tasks.md 任务依赖存在循环: T1 -> T2 -> T1", "\n".join(errors))

    def test_task_breakdown_rejects_manual_release_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            text = build_tasks_doc().replace("实现报告提交服务", "发布和回滚准备")
            path.write_text(text, encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        self.assertIn("03-tasks.md T1 不是仓库编码任务: 发布和回滚准备", "\n".join(errors))

    def test_task_breakdown_requires_substantive_task_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            text = build_tasks_doc().replace(
                "- 主要实现内容：\n  - 按 reportId 保存并返回报告记录。\n  - interface-details/02-interface-01-submit.md 对应的入参和结果由该服务承载。",
                "- 主要实现内容：\n  -",
            ).replace(
                "- 代码边界：\n  - 不改变其他报告查询链路。",
                "- 代码边界：\n  -",
            )
            path.write_text(text, encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        error_text = "\n".join(errors)
        self.assertIn("03-tasks.md T1 任务详情的主要实现内容不能为空", error_text)
        self.assertIn("03-tasks.md T1 任务详情的代码边界不能为空", error_text)

    def test_task_breakdown_requires_interface_and_schema_code_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "03-tasks.md"
            detail_dir = root / "interface-details"
            detail_dir.mkdir()
            (detail_dir / "02-interface-02-query.md").write_text("# query", encoding="utf-8")
            path.write_text(build_tasks_doc(), encoding="utf-8")

            errors = validate_tasks_doc(
                path,
                interface_details=detail_dir,
                valid_design_ids={"D1"},
                valid_claim_ids={"C1"},
                schema_exists=True,
            )

        error_text = "\n".join(errors)
        self.assertIn("03-tasks.md 缺少接口明细对应编码任务: 02-interface-02-query.md", error_text)
        self.assertIn("03-tasks.md 存在 04-schema.sql，但没有编码任务覆盖 SQL 文件及持久化代码", error_text)

    def test_clarification_defaults_backfill_new_gate_keys(self) -> None:
        meta = {
            "gates": {
                "alignment_completed": True,
                "design_confirmed": True,
            },
            "review_flags": {},
        }

        gates, review_flags = ensure_defaults(meta)

        self.assertTrue(gates["alignment_completed"])
        self.assertTrue(gates["design_confirmed"])
        self.assertFalse(gates["tasks_confirmed"])
        self.assertFalse(gates["implementation_completed"])
        self.assertFalse(gates["review_passed"])
        self.assertFalse(gates["test_passed"])
        self.assertFalse(gates["release_ready"])
        self.assertFalse(gates["clarification_required"])
        self.assertFalse(gates["clarification_confirmed"])
        self.assertFalse(review_flags["alignment_needs_review"])

    def test_task_breakdown_template_examples_do_not_satisfy_traceability(self) -> None:
        errors = validate_tasks_doc(
            ASSET_ROOT / "templates" / "task-breakdown-template.md",
            valid_design_ids={"D1"},
            valid_claim_ids={"C1"},
            schema_exists=True,
        )
        error_text = "\n".join(errors)

        self.assertIn("03-tasks.md 任务总览缺少结构化任务行", error_text)

    def test_execution_templates_match_contract(self) -> None:
        template_checks = [
            ("implementation-log-template.md", IMPLEMENTATION_LOG_REQUIRED_TOKENS),
            ("code-review-index-template.md", CODE_REVIEW_INDEX_REQUIRED_TOKENS),
            ("code-review-round-template.md", CODE_REVIEW_ROUND_REQUIRED_TOKENS),
            ("test-report-index-template.md", TEST_REPORT_INDEX_REQUIRED_TOKENS),
            ("test-report-round-template.md", TEST_REPORT_ROUND_REQUIRED_TOKENS),
        ]
        for template_name, tokens in template_checks:
            text = (ASSET_ROOT / "templates" / template_name).read_text(encoding="utf-8")
            for token in tokens:
                self.assertIn(token, text)

    def test_interface_detail_template_matches_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "interface-detail-template.md").read_text(encoding="utf-8")
        for token in INTERFACE_DETAIL_V3_REQUIRED_TOKENS:
            self.assertIn(token, text)
        self.assertIn("GGG_INTERFACE_SCHEMA_VERSION: 3", text)

    def test_init_keeps_existing_workflow_assets_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            templates_dir = repo_root / "ggg" / "workflow" / "templates"
            templates_dir.mkdir(parents=True, exist_ok=True)
            readme_path = repo_root / "ggg" / "workflow" / "README.md"
            baseline_template_path = templates_dir / "baseline-template.md"
            readme_path.write_text("custom readme\n", encoding="utf-8")
            baseline_template_path.write_text("custom baseline template\n", encoding="utf-8")

            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "init_feature_docs.py"), "--repo-root", str(repo_root), "--feature-name", "示例需求"],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(readme_path.read_text(encoding="utf-8"), "custom readme\n")
            self.assertEqual(baseline_template_path.read_text(encoding="utf-8"), "custom baseline template\n")
            meta_path = next((repo_root / "ggg" / "features").glob("*/meta.json"))
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(4, meta["workflow_schema_version"])
            self.assertTrue(meta["gates"]["clarification_required"])
            self.assertFalse(meta["gates"]["clarification_confirmed"])
            feature_baseline = meta_path.parent / "00-baseline.md"
            self.assertIn("GGG_SCHEMA_VERSION: 4", feature_baseline.read_text(encoding="utf-8"))

    def test_init_quick_record_creates_lightweight_record_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "init-quick",
                    "--repo-root",
                    str(repo_root),
                    "--quick-name",
                    "示例小需求",
                    "--date",
                    "20260703",
                    "--create-schema",
                    "--interface-name",
                    "查询学习包",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            quick_path = repo_root / "ggg" / "features" / "20260703-示例小需求" / "quick.md"
            self.assertTrue(quick_path.exists())
            quick_text = quick_path.read_text(encoding="utf-8")
            self.assertIn("Quick 小需求记录：示例小需求", quick_text)
            self.assertIn("<!-- GGG_QUICK_SCHEMA_VERSION: 2 -->", quick_text)
            self.assertFalse((quick_path.parent / "meta.json").exists())
            self.assertTrue((quick_path.parent / "04-schema.sql").exists())
            interface_paths = list((quick_path.parent / "interface-details").glob("02-interface-*-查询学习包.md"))
            self.assertEqual(1, len(interface_paths))
            self.assertIn("不进入 full 需求状态机", completed.stdout)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "init-quick",
                    "--repo-root",
                    str(repo_root),
                    "--quick-name",
                    "示例小需求",
                    "--date",
                    "20260703",
                    "--interface-name",
                    "查询学习包",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                1,
                len(list((quick_path.parent / "interface-details").glob("02-interface-*-查询学习包.md"))),
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "init_feature_docs.py"),
                    "--repo-root",
                    str(repo_root),
                    "--feature-name",
                    "示例小需求",
                    "--date",
                    "20260703",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            validation_errors = validate_feature_dir(quick_path.parent)
            self.assertNotIn("04-schema.sql 不应在当前阶段提前生成", validation_errors)
            self.assertNotIn("interface-details/ 不应在当前阶段提前生成", validation_errors)

    def test_init_defaults_to_current_git_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            nested_dir = repo_root / "module" / "src"
            nested_dir.mkdir(parents=True)
            subprocess.run(
                ["git", "init", str(repo_root)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "init-quick",
                    "--quick-name",
                    "默认根目录小需求",
                    "--date",
                    "20260704",
                ],
                cwd=nested_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "init",
                    "--feature-name",
                    "默认根目录正式需求",
                    "--date",
                    "20260705",
                ],
                cwd=nested_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertTrue(
                (repo_root / "ggg" / "features" / "20260704-默认根目录小需求" / "quick.md").exists()
            )
            self.assertTrue(
                (repo_root / "ggg" / "features" / "20260705-默认根目录正式需求" / "meta.json").exists()
            )
            self.assertFalse((nested_dir / "ggg").exists())

    def test_to_tasks_requires_valid_design_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            feature_dir = repo_root / "ggg" / "features" / "20260319-示例需求"
            workflow_dir = repo_root / "ggg" / "workflow" / "templates"
            feature_dir.mkdir(parents=True, exist_ok=True)
            workflow_dir.mkdir(parents=True, exist_ok=True)

            for template_name in [
                "baseline-template.md",
                "requirement-research-template.md",
                "technical-design-template.md",
                "task-breakdown-template.md",
            ]:
                source = ASSET_ROOT / "templates" / template_name
                target = workflow_dir / template_name
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

            meta = {
                "feature_name": "示例需求",
                "current_phase": "技术方案",
                "current_status": "方案中",
                "primary_project": "demo-service",
                "blocking_issue_count": 0,
                "gates": {
                    "alignment_completed": True,
                    "design_confirmed": False,
                    "business_model_confirmed": False,
                    "upstream_contract_confirmed": False,
                },
                "review_flags": {
                    "alignment_needs_review": False,
                    "design_needs_review": False,
                    "tasks_needs_review": False,
                },
                "clarification": {
                    "count": 0,
                    "last_source": "",
                    "last_summary": "",
                    "last_updated_at": "",
                    "last_impacts": [],
                },
                "documents": {
                    "baseline": "00-baseline.md",
                    "research": "01-research.md",
                    "design": "02-design.md",
                    "interface_details": "interface-details/",
                    "tasks": "03-tasks.md",
                    "schema": "04-schema.sql",
                },
            }
            (feature_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (feature_dir / "00-baseline.md").write_text(
                """# 全局基线文档模板

## 1. 基本信息

- 主项目：demo-service
- 主项目判断依据：controller 和 service 都在 demo-service，链路明确

## 4. 需求理解摘要

- 核心流程：提交请求后写入结果并返回
- 输入对象：reportId、userId
- 输出对象：提交结果

## 5. 范围边界

- 本期包含：主链路改造
- 本期不做：管理后台重构
- 原因：本期只处理核心接口

## 6. 代码现状结论

- 旧逻辑集中在 demo-service 的 ReportController 和 ReportService。

## 8. 决策记录

| 编号 | 决策主题 | 备选方案 | 最终选择 | 为什么不选其他方案 | 影响范围 | 工作量 | 决策来源 |
|---|---|---|---|---|---|---|---|
| DEC1 | 主项目 | A / B | demo-service | 旧逻辑集中 | 报告链路 | 中 | 代码 |

## 12. 代码证据索引

| 编号 | 项目 | 类型 | 位置 | 结论说明 |
|---|---|---|---|---|
| E1 | demo-service | Controller | ReportController.java | 主入口在 demo-service |

## 13. 当前阻塞项

| 编号 | 问题 | 原因 | 需要谁确认 | 状态 |
|---|---|---|---|---|
| Q1 | 无 | 已确认 | 产品 | 已确认 |

## 15. 下一步动作

1. 深入核对旧链路。
2. 收口接口契约。
""",
                encoding="utf-8",
            )
            (feature_dir / "01-research.md").write_text(
                """# 代码调研

## 1. 调研范围

- 调研目标：确认主链路与数据落点

## 2. 入口与核心对象

### 2.4 主项目判断依据

- PRD 线索：报告提交入口在 demo-service。
- 结论：demo-service 是主项目。

## 3. 旧链路梳理

### 3.1 主链路

- 主链路文本：ReportController -> ReportService -> ReportFacade -> report_record

### 3.2 关键逻辑

- ReportService 负责参数组装和主规则判断。

### 3.3 风险点

- 依赖 Facade 返回结构存在历史兼容分支。

### 3.4 关键代码证据

| 编号 | 结论 | 证据位置 | 备注 |
|---|---|---|---|
| E1 | 主链路在 demo-service | ReportService.java | 已核对 |

## 4. 选型与差异分析

### 4.3 数据归属与落点

| 数据 / 字段 | 当前来源 | 当前落点 | 是否复用 | 说明 |
|---|---|---|---|---|
| reportId | 请求参数 | report_record | 是 | 主表主键 |

## 5. 需确认项

| 编号 | 问题 | 当前判断 | 推荐方案 | 备选方案 | 风险 | 工作量 | 是否阻塞 | 是否已沟通 |
|---|---|---|---|---|---|---|---|---|
| Q1 | 无 | 已确认 | 继续推进 | 无 | 低 | 低 | 否 | 是 |

## 6. 调研结论

- 推荐方案：沿用 demo-service 主链路扩展。
- 对技术方案最重要的输入：Facade 契约和表落点已明确。
- 是否可以进入技术方案阶段：是。
""",
                encoding="utf-8",
            )
            (feature_dir / "02-design.md").write_text(
                (ASSET_ROOT / "templates" / "technical-design-template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "advance_feature_phase.py"),
                    "--feature-dir",
                    str(feature_dir),
                    "--to-phase",
                    "任务拆分",
                    "--design-confirmed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("未通过校验", completed.stdout)

    def test_test_report_completion_requires_scenario_traceability_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp)
            (feature_dir / "00-baseline.md").write_text(
                build_confirmed_baseline(),
                encoding="utf-8",
            )
            evidence_sha = write_test_evidence(feature_dir)
            rounds_dir = feature_dir / "test-rounds"
            rounds_dir.mkdir()
            (feature_dir / "07-test-report.md").write_text(
                build_completed_test_index(),
                encoding="utf-8",
            )
            round_path = rounds_dir / "test-r01.md"
            round_path.write_text(
                build_completed_test_round(
                    baseline_ids=("B1", "B2", "B3", "B4", "B5"),
                    diff_paths=("src/ReportController.java", "src/ReportResponse.java"),
                    evidence_sha=evidence_sha,
                ),
                encoding="utf-8",
            )

            errors = validate_test_report_completion(
                feature_dir / "07-test-report.md",
                rounds_dir,
                expected_implementation_round="I1",
                expected_fingerprint="a" * 64,
                expected_review_round="R1",
                actual_paths={"src/ReportController.java", "src/ReportResponse.java"},
            )
            self.assertEqual([], errors)

            round_path.write_text(
                round_path.read_text(encoding="utf-8").replace(
                    "| read-only | 通过 | E1；HTTP 200；",
                    "| read-only | 未执行 | 缺管理员 token；",
                ),
                encoding="utf-8",
            )
            errors = validate_test_report_completion(feature_dir / "07-test-report.md", rounds_dir)
            self.assertIn(
                "test-r01.md TS1 是关键场景，必须验证通过",
                "\n".join(errors),
            )

    def test_formal_gate_manifest_must_cover_every_baseline_and_real_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            (feature / "00-baseline.md").write_text(build_confirmed_baseline(), encoding="utf-8")
            evidence_sha = write_test_evidence(feature)
            (feature / "07-test-report.md").write_text(build_completed_test_index(), encoding="utf-8")
            rounds = feature / "test-rounds"
            rounds.mkdir()
            (rounds / "test-r01.md").write_text(
                build_completed_test_round(
                    baseline_ids=("B1",),
                    diff_paths=("src/ReportController.java",),
                    evidence_sha=evidence_sha,
                ),
                encoding="utf-8",
            )
            errors = validate_test_report_completion(
                feature / "07-test-report.md",
                rounds,
                actual_paths={"src/ReportController.java", "src/ReportResponse.java"},
            )
        error_text = "\n".join(errors)
        self.assertIn("来源 Manifest 遗漏基线项: B2, B3, B4, B5", error_text)
        self.assertIn("来源 Manifest 遗漏真实 Diff 文件: src/ReportResponse.java", error_text)

    def test_formal_gate_execution_evidence_requires_protocol_result_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            write_test_evidence(feature)
            (feature / "07-test-report.md").write_text(build_completed_test_index(), encoding="utf-8")
            rounds = feature / "test-rounds"
            rounds.mkdir()
            round_text = build_completed_test_round(
                evidence_sha="e" * 64,
            )
            (rounds / "test-r01.md").write_text(round_text, encoding="utf-8")
            errors = validate_test_report_completion(feature / "07-test-report.md", rounds)
        self.assertIn("E1 证据 SHA-256 与真实文件不一致", "\n".join(errors))

    def test_run_only_cannot_be_recorded_as_formal_gate_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            evidence_sha = write_test_evidence(feature)
            (feature / "07-test-report.md").write_text(
                build_completed_test_index().replace(
                    "- 当前模式：formal-gate",
                    "- 当前模式：run-only",
                ),
                encoding="utf-8",
            )
            rounds = feature / "test-rounds"
            rounds.mkdir()
            (rounds / "test-r01.md").write_text(
                build_completed_test_round(evidence_sha=evidence_sha).replace(
                    "- 测试模式：formal-gate",
                    "- 测试模式：run-only",
                ),
                encoding="utf-8",
            )
            errors = validate_test_report_completion(feature / "07-test-report.md", rounds)
        error_text = "\n".join(errors)
        self.assertIn("正式通过只能来自 formal-gate", error_text)
        self.assertIn("正式通过必须使用 formal-gate", error_text)

    def test_nonpass_formal_gate_keeps_reproducible_evidence_and_open_tv(self) -> None:
        gap = (
            "| TV1 | T1 | TS1 | 测试数据缺失导致业务断言失败 | 关键 | 环境或数据问题 | "
            "open | E1 原始响应已落盘 | 测试验证；补齐数据后复验 |"
        )
        ledger = (
            "| TV1 | T1 | T1 | 测试数据缺失导致业务断言失败 | 环境或数据问题 | "
            "open |  | 补齐数据后复验 |"
        )
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            evidence_sha = write_test_evidence(feature, b"HTTP 500 missing fixture\n")
            index = (
                build_completed_test_index(gap_rows=ledger)
                .replace("| formal-gate | 通过 |", "| formal-gate | 需补测 |")
                .replace("- 当前结论：通过", "- 当前结论：需补测")
            )
            (feature / "07-test-report.md").write_text(index, encoding="utf-8")
            rounds = feature / "test-rounds"
            rounds.mkdir()
            round_text = (
                build_completed_test_round(gap_rows=gap, evidence_sha=evidence_sha)
                .replace("- 结论：通过", "- 结论：需补测")
                .replace("- 测试阶段是否完成：是", "- 测试阶段是否完成：否")
                .replace("- 主要失败归因：无", "- 主要失败归因：环境或数据问题")
                .replace("- 建议返回阶段：无", "- 建议返回阶段：测试验证")
                .replace("- 复验条件：无", "- 复验条件：补齐测试数据后重跑 TS1")
                .replace("| read-only | 通过 | E1；HTTP 200；", "| read-only | 失败 | E1；HTTP 500；")
                .replace("| HTTP 200 code=0 | 提交成功且结果字段正确 |", "| HTTP 500 | 缺少测试数据 |")
                .replace("| PASS |", "| FAIL |")
            )
            (rounds / "test-r01.md").write_text(round_text, encoding="utf-8")
            errors = validate_test_report_nonpass(
                feature / "07-test-report.md",
                rounds,
                result="needs_more",
                expected_implementation_round="I1",
                expected_fingerprint="a" * 64,
                expected_review_round="R1",
            )
        self.assertEqual([], errors)

    def test_test_gap_history_requires_tv_to_continue_across_rounds(self) -> None:
        open_gap = (
            "| TV1 | T1 | TS1 | 环境数据缺失 | 一般 | 环境或数据问题 | "
            "open | logs/t1.log dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd | "
            "测试验证；补齐数据后复验 |"
        )
        fixed_gap = (
            "| TV1 | T1 | TS1 | 环境数据缺失 | 一般 | 环境或数据问题 | "
            "fixed | T2 E1 已补齐数据并通过 | 无需返回；已复验 |"
        )
        ledger = (
            "| TV1 | T1 | T2 | 环境数据缺失 | 环境或数据问题 | "
            "fixed | T2 E1 | 已完成复验 |"
        )
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            evidence_sha = write_test_evidence(feature)
            (feature / "07-test-report.md").write_text(
                build_completed_test_index(round_id="T2", gap_rows=ledger),
                encoding="utf-8",
            )
            rounds = feature / "test-rounds"
            rounds.mkdir()
            (rounds / "test-r01.md").write_text(
                build_completed_test_round(gap_rows=open_gap, evidence_sha=evidence_sha),
                encoding="utf-8",
            )
            second = rounds / "test-r02.md"
            second.write_text(
                build_completed_test_round(
                    round_id="T2",
                    gap_rows=fixed_gap,
                    evidence_sha=evidence_sha,
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                [],
                validate_test_report_completion(feature / "07-test-report.md", rounds),
            )
            second.write_text(
                build_completed_test_round(round_id="T2", evidence_sha=evidence_sha),
                encoding="utf-8",
            )
            errors = validate_test_report_completion(feature / "07-test-report.md", rounds)
        self.assertIn("最新测试轮次未继承上轮未关闭 TVxx: TV1", "\n".join(errors))

    def test_test_artifact_fingerprint_includes_api_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            record = feature / "05-implementation-log.md"
            record.write_text(build_completed_implementation_log(), encoding="utf-8")
            (feature / "07-test-report.md").write_text(build_completed_test_index(), encoding="utf-8")
            rounds = feature / "test-rounds"
            rounds.mkdir()
            (rounds / "test-r01.md").write_text(build_completed_test_round(), encoding="utf-8")
            api_dir = feature / "reports" / "api-tests"
            api_dir.mkdir(parents=True)
            api_report = api_dir / "submit.md"
            api_report.write_text("response-v1\n", encoding="utf-8")
            before = test_artifact_fingerprint(record)
            api_report.write_text("response-v2\n", encoding="utf-8")
            self.assertNotEqual(before, test_artifact_fingerprint(record))

    def test_test_status_becomes_stale_when_evidence_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            code = repo / "app.txt"
            code.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
            base_head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            code.write_text("after\n", encoding="utf-8")
            repositories = [
                {
                    "root": str(repo),
                    "label": "repo",
                    "base_head": base_head,
                    "initial_dirty": {},
                    "adopted_existing": [],
                }
            ]
            code_fingerprint = current_snapshot(
                {"schema_version": 6, "repositories": repositories}
            )["fingerprint"]

            feature = root / "feature"
            feature.mkdir()
            record = feature / "05-implementation-log.md"
            record.write_text(build_completed_implementation_log(), encoding="utf-8")
            review_rounds = feature / "review-rounds"
            review_rounds.mkdir()
            (feature / "06-code-review.md").write_text(
                build_completed_review_index(),
                encoding="utf-8",
            )
            (review_rounds / "review-r01.md").write_text(
                build_completed_review_round(paths=("app.txt",)),
                encoding="utf-8",
            )
            evidence_sha = write_test_evidence(feature)
            (feature / "07-test-report.md").write_text(
                build_completed_test_index(),
                encoding="utf-8",
            )
            test_rounds = feature / "test-rounds"
            test_rounds.mkdir()
            (test_rounds / "test-r01.md").write_text(
                build_completed_test_round(
                    baseline_ids=(),
                    diff_paths=("app.txt",),
                    evidence_sha=evidence_sha,
                    fingerprint=code_fingerprint,
                ),
                encoding="utf-8",
            )

            state = {
                "schema_version": 6,
                "record": str(record),
                "round": "I1",
                "status": "completed",
                "repositories": repositories,
                "review": None,
                "test": None,
            }
            snapshot = current_snapshot(state)
            state["completion_snapshot"] = snapshot
            state["review"] = {
                "implementation_round": "I1",
                "fingerprint": snapshot["fingerprint"],
                "review_round": "R1",
                "input_fingerprint": review_input_fingerprint(
                    record,
                    snapshot["fingerprint"],
                ),
                "artifact_fingerprint": review_artifact_fingerprint(record),
                "result": "passed",
            }
            (feature / "implementation-state.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            marked = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "test-mark",
                    "--record",
                    str(record),
                    "--result",
                    "passed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, marked.returncode, marked.stdout + marked.stderr)

            (feature / "reports" / "evidence" / "e1.log").write_bytes(b"tampered\n")
            status = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "test-status",
                    "--record",
                    str(record),
                    "--require-passed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, status.returncode)
            self.assertIn("测试记录在登记结论后发生变化", status.stdout)

    def test_quick_test_evidence_rejects_technical_only_or_empty_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            quick = Path(tmp) / "quick.md"
            quick.write_text(
                """# Quick

- 测试结论：通过

### 5.2 Quick 测试场景

| 场景ID | 来源依据 | 业务场景 | 级别 | 前置条件 | 操作与测试数据 | 预期结果 | Effect | 结果 | 证据或原因 |
|---|---|---|---|---|---|---|---|---|---|
| TS1 | 边界目标；Review 通过 | 管理员下架学习包 | 关键 | 学习包已上架 | 下架 packageId=1001 | 状态变为下架 | read-only | 通过 | HTTP 200；响应与回查；SHA-256 dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd |
""",
                encoding="utf-8",
            )
            self.assertEqual([], validate_quick_test_evidence(quick))

            quick.write_text(
                quick.read_text(encoding="utf-8").replace(
                    "| TS1 | 边界目标；Review 通过 | 管理员下架学习包 | 关键 | 学习包已上架 | 下架 packageId=1001 | 状态变为下架 | read-only | 通过 | HTTP 200；响应与回查；SHA-256 dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd |",
                    "| TS1 |  | 测试 Service | 一般 |  |  |  | unknown | 已验证 |  |",
                ),
                encoding="utf-8",
            )
            error_text = "\n".join(validate_quick_test_evidence(quick))
            self.assertIn("缺少可追溯的来源依据", error_text)
            self.assertIn("至少需要一个由验收目标推导的关键场景", error_text)
            self.assertIn("结果必须为", error_text)

    def test_test_mark_binds_quick_result_and_detects_code_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            code_path = repo / "app.txt"
            code_path.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
            base_head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            code_path.write_text("after\n", encoding="utf-8")

            feature_dir = repo / "ggg" / "features" / "quick-demo"
            feature_dir.mkdir(parents=True)
            quick = feature_dir / "quick.md"
            quick.write_text(
                """# Quick

- 测试结论：通过
- 测试对应实现轮次：
- 测试对应差异指纹：

### 5.2 Quick 测试场景

| 场景ID | 来源依据 | 业务场景 | 级别 | 前置条件 | 操作与测试数据 | 预期结果 | Effect | 结果 | 证据或原因 |
|---|---|---|---|---|---|---|---|---|---|
| TS1 | 边界目标；Review 通过；diff: app.txt | 修改后文本可读取 | 关键 | 文件存在 | 读取 app.txt | 内容为 after | read-only | 通过 | exit=0；输出 after；SHA-256 dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd |
""",
                encoding="utf-8",
            )
            state = {
                "schema_version": 4,
                "record": str(quick),
                "round": "I1",
                "status": "completed",
                "repositories": [
                    {
                        "root": str(repo),
                        "label": "repo",
                        "base_head": base_head,
                        "initial_dirty": {},
                        "adopted_existing": [],
                    }
                ],
                "review": None,
                "test": None,
            }
            snapshot = current_snapshot(state)
            state["completion_snapshot"] = snapshot
            state["review"] = {
                "implementation_round": "I1",
                "fingerprint": snapshot["fingerprint"],
                "result": "passed",
            }
            (feature_dir / "implementation-state.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            marked = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "test-mark",
                    "--record",
                    str(quick),
                    "--result",
                    "passed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, marked.returncode, marked.stdout + marked.stderr)
            updated_state = json.loads(
                (feature_dir / "implementation-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual("passed", updated_state["test"]["result"])
            self.assertIn("- 测试对应实现轮次：I1", quick.read_text(encoding="utf-8"))

            code_path.write_text("changed-after-test\n", encoding="utf-8")
            status = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "workflow_cli.py"),
                    "test-status",
                    "--record",
                    str(quick),
                    "--require-passed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, status.returncode)
            self.assertIn("[STALE]", status.stdout)


if __name__ == "__main__":
    unittest.main()
