from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
WORKFLOW_ROOT = TEST_DIR.parent
SCRIPTS_DIR = WORKFLOW_ROOT / "scripts"
ASSET_ROOT = WORKFLOW_ROOT / "assets" / "workflow"

sys.path.insert(0, str(SCRIPTS_DIR))

from workflow_contracts import (
    BASELINE_REQUIRED_TOKENS,
    CODE_REVIEW_INDEX_REQUIRED_TOKENS,
    CODE_REVIEW_ROUND_REQUIRED_TOKENS,
    DESIGN_REQUIRED_TOKENS,
    IMPLEMENTATION_LOG_REQUIRED_TOKENS,
    INTERFACE_DETAIL_REQUIRED_TOKENS,
    QUICK_RECORD_REQUIRED_TOKENS,
    RESEARCH_REQUIRED_TOKENS,
    TEST_REPORT_INDEX_REQUIRED_TOKENS,
    TEST_REPORT_ROUND_REQUIRED_TOKENS,
)
from workflow_validation import validate_design_doc, validate_research_doc, validate_tasks_doc
from sync_clarification_impact import ensure_defaults


def build_research_doc(evidence_location: str, claim_evidence_id: str = "E1") -> str:
    return f"""# 代码调研

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

## 8. 代码证据覆盖度、运行时证据缺口和置信度

| 结论ID | 证据来源 | 证据等级 | 已覆盖代码 | 未覆盖范围 | 运行时证据缺口 | 置信度 | 后续确认方式 |
|---|---|---|---|---|---|---|---|
| C1 | CodeGraph | 代码已证实 | ReportController -> ReportService | Nacos 开关 | 配置确认 | 高 | 配置确认 |

## 9. 结论账本（Claim Ledger）

| 结论ID | 关键结论 | 结论类型 | 证据ID | 证据等级 | 置信度 | 未覆盖范围 | 若结论错误的影响 | 后续确认方式 |
|---|---|---|---|---|---|---|---|---|
| C1 | ReportService 可扩展复用 | 复用边界 | {claim_evidence_id} | 代码已证实 | 高 | Nacos 开关 | 影响旧链路 | 配置确认 |

## 10. 进入技术方案前阻塞问题

| 编号 | 问题 | 当前判断 | 推荐方案 | 是否阻塞 |
|---|---|---|---|---|
| Q1 | 无 | 已确认 | 进入方案 | 否 |

## 11. 残余风险和后续确认方式

- 已确认：主链路已覆盖。
- 未覆盖：Nacos 开关待配置确认。

## 12. 代码证据索引

| 编号 | 项目 | 类型 | 位置 | 结论说明 |
|---|---|---|---|---|
| E1 | demo-service | Controller | {evidence_location} | 主入口 |
"""


def build_design_doc(source_claim: str = "C1") -> str:
    return f"""# 技术方案

## 一、背景与目标

- 目标：提交报告。

## 二、实例身份与状态隔离

| 业务对象/记录 | 唯一标识 | 状态隔离维度 | 去重维度 | 生命周期 | 来源证据 | 是否已确认 |
|---|---|---|---|---|---|---|
| 报告 | reportId | userId + reportId | reportId | 创建到完成 | {source_claim} | 是 |

## 三、前后端接口协作流

| 页面/动作 | 调用接口 | 首屏/点击后 | 请求关键字段 | 后端自动推导 | 前端禁止传 | 返回粒度 | 说明 |
|---|---|---|---|---|---|---|---|
| 提交 | submit | 提交后 | reportId | userId | userId | 结果 | {source_claim} |

## 四、数据承载设计

| 数据/状态 | 承载方式 | MySQL | Redis | ES | MQ | 配置/缓存 | 选择原因 | 一致性/过期策略 |
|---|---|---|---|---|---|---|---|---|
| 报告记录 | MySQL | 是 | 否 | 否 | 否 | 否 | {source_claim} | 事务提交 |

## 五、SQL 表设计

### 5.1 SQL 字段风格参考

| 参考项目/模块 | 参考表 | 公共字段风格 | 逻辑删除字段 | 时间字段 | 用户字段口径 | 索引命名风格 | 说明 |
|---|---|---|---|---|---|---|---|
| demo | report_record | id/create_time | is_delete | create_time | create_user | idx_xxx | {source_claim} |

### 5.2 `user_id` 设计判断

| 是否需要 `user_id` | 用户语义 | 身份来源 | 是否前端可传 | 是否后端推导 | 是否参与唯一键/索引 | 与实例身份关系 | 说明 |
|---|---|---|---|---|---|---|---|
| 是 | 学生 | 登录态 | 否 | 是 | 是 | 隔离维度 | {source_claim} |

### 5.3 SQL 瘦身检查

#### 表准入

| 表 | 业务事实 | 写入事件 | 查询场景 | 生命周期 | 能否复用旧表 | 不建表后果 |
|---|---|---|---|---|---|---|
| report_record | 报告记录 | 提交 | 查询 | 长期 | 是 | 无法查询 |

#### 字段准入

| 表 | 字段 | 来源 | 写入时机 | 读取场景 | 是否可推导 | 是否参与查询/唯一键/索引 | 不落库后果 |
|---|---|---|---|---|---|---|---|
| report_record | report_id | 请求 | 提交 | 查询 | 否 | 是 | 无法定位 |

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

| 设计ID | 接口名称 | 新增/修改 | 请求方式 | 路径/方法 | 所属项目 | 首屏/点击后/提交后 | 接口文档地址 | 来源Cxx | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| D1 | 提交 | 修改 | POST | /submit | demo | 提交后 | interface-details/02-interface-01-submit.md | {source_claim} | 复用 |

## 九、枚举、状态与常量

| 名称 | 所属项目/类 | 类型 | 取值 | 用途 | 新增/修改 |
|---|---|---|---|---|---|
| Status | demo | Enum | 1 | 状态 | 复用 |

## 十三、设计决策记录

| 设计ID | 决策点 | 选择 | 不选方案 | 来源Cxx | 原因 | 影响 |
|---|---|---|---|---|---|---|
| D1 | 提交链路 | 复用 ReportService | 新增 Service | {source_claim} | 主链路一致 | Service |

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


def build_tasks_doc(source: str = "D1 / C1") -> str:
    return f"""# 任务拆分

## 1. 实施概览

- 主项目：demo
- 依赖项目：无

## 2. 输入覆盖清单

| 来源 | 条目 | 来源依据 | 对应任务 | 是否覆盖 |
|---|---|---|---|---|
| `02-design.md` | 提交链路 | {source} | T1 | 是 |

## 3. 拆分原则、状态和排期顺序

- 拆分原则：按主链路。
- 串行关键路径：T1
- 可并行组：P2
- 并行执行等级：L2
- 不并行原因（L0 必填）：不适用
- 阻塞任务：无
- 推荐执行顺序：T1

并行安全评估矩阵：

| 任务 | 并行组 | 预计写入文件/目录 | 共享依赖 | 契约/表/配置影响 | 冲突结论 | 执行方式 |
|---|---|---|---|---|---|---|
| T1 | P2 | src/main/java/demo/ReportService.java | 无 | 无 | 可并行 | 并行 |

多 agent 并行编码分配表：

| Worker | 任务 | 允许修改文件/目录 | 禁止修改文件/目录 | 只读参考文件/目录 | 依赖任务 | 合并顺序 | 验证命令 |
|---|---|---|---|---|---|---|---|
| W1 | T1 | src/main/java/demo/ReportService.java | src/main/resources/application.yml | src/main/java/demo/ReportController.java | - | 1 | mvn test |

## 4. 任务总览

| 编号 | 任务 | 类型 | 来源依据 | 所属项目 | 主要落点 | 预计写入文件/目录 | 依赖 | 可并行组 | 初始状态 | 输出物 | 完成标准 | 工作量 | 协作方 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | 实现提交 | Service | {source} | demo | ReportService | src/main/java/demo/ReportService.java | - | P2 | ready | 代码 | 编译通过 | 低 | 后端 |

## 5. 详细任务

### 5.1 P0 前置任务
- 无：无前置。
### 5.2 P1 基础代码任务
- 无：无基础改动。
### 5.3 P2 核心业务任务
- T1：
  - 来源依据：{source}
  - 依赖：无
  - 主要落点：ReportService
  - 输出物：代码
  - 完成标准：编译通过
### 5.4 P3 接口与契约任务
- 无：接口不变。
### 5.5 P4 测试、回归、发布和回滚
- T2：
  - 来源依据：{source}
  - 依赖：T1
  - 验证场景：主流程
  - 输出物：报告
  - 完成标准：通过

## 6. 接口、风险和测试映射

### 6.1 接口映射

| 接口文档 | 来源依据 | 实现任务 | 测试任务 | 说明 |
|---|---|---|---|---|
| interface-details/02-interface-01-submit.md | {source} | T1 | T2 | 提交 |

### 6.2 风险映射

| 风险点 | 来源 | 来源依据 | 防护/实现任务 | 验证/回归任务 | 说明 |
|---|---|---|---|---|---|
| 配置 | `02-design.md` | {source} | T1 | T2 | 确认 |

### 6.3 SQL / 配置 / 缓存 / MQ 验证映射

| 变更项 | 类型 | 来源依据 | 实现任务 | 验证任务 | 回滚动作 |
|---|---|---|---|---|---|
| 无 | 配置 | {source} | T1 | T2 | 无 |

## 7. 范围裁剪

- 本期不做：无
- 后续建议：无

## 8. 完成定义

- 所有任务有来源依据。
- 所有任务有完成标准。
- 每个接口明细都有实现任务和测试任务。
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
        self.assertIn("init-quick", completed.stdout)
        self.assertIn("to-design", completed.stdout)
        self.assertIn("to-tasks", completed.stdout)
        self.assertIn("to-implementation", completed.stdout)
        self.assertIn("to-review", completed.stdout)
        self.assertIn("to-test", completed.stdout)
        self.assertIn("complete", completed.stdout)

    def test_technical_design_template_matches_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "technical-design-template.md").read_text(encoding="utf-8")
        for token in DESIGN_REQUIRED_TOKENS:
            self.assertIn(token, text)

    def test_quick_record_template_matches_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "quick-record-template.md").read_text(encoding="utf-8")
        for token in QUICK_RECORD_REQUIRED_TOKENS:
            self.assertIn(token, text)

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

    def test_requirement_research_template_matches_contract(self) -> None:
        text = (ASSET_ROOT / "templates" / "requirement-research-template.md").read_text(encoding="utf-8")
        for token in RESEARCH_REQUIRED_TOKENS:
            self.assertIn(token, text)

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

## 8. 代码证据覆盖度、运行时证据缺口和置信度

| 结论ID | 证据来源 | 证据等级 | 已覆盖代码 | 未覆盖范围 | 运行时证据缺口 | 置信度 | 后续确认方式 |
|---|---|---|---|---|---|---|---|
| C1 | CodeGraph | 代码已证实 | ReportController -> ReportService | Nacos 开关 | 配置确认 | 高 | 配置确认 |

## 9. 结论账本（Claim Ledger）

| 结论ID | 关键结论 | 结论类型 | 证据ID | 证据等级 | 置信度 | 未覆盖范围 | 若结论错误的影响 | 后续确认方式 |
|---|---|---|---|---|---|---|---|---|
| C1 | ReportService 可扩展复用 | 复用边界 | E2 | 代码已证实 | 高 | Nacos 开关 | 影响旧链路 | 配置确认 |

## 10. 进入技术方案前阻塞问题

| 编号 | 问题 | 当前判断 | 推荐方案 | 是否阻塞 |
|---|---|---|---|---|
| Q1 | 无 | 已确认 | 进入方案 | 否 |

## 11. 残余风险和后续确认方式

- 已确认：主链路已覆盖。
- 未覆盖：Nacos 开关待配置确认。

## 12. 代码证据索引

| 编号 | 项目 | 类型 | 位置 | 结论说明 |
|---|---|---|---|---|
| E1 | demo-service | Controller | ReportController.java:18 | 主入口 |
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "01-research.md"
            path.write_text(research_text, encoding="utf-8")

            errors = validate_research_doc(path)

        self.assertIn("01-research.md C1 引用了不存在于代码证据索引的证据ID: E2", "\n".join(errors))

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

    def test_task_breakdown_detail_and_mapping_require_traceable_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            text = build_tasks_doc("D1 / C1")
            text = text.replace(
                "  - 来源依据：D1 / C1\n  - 依赖：无",
                "  - 来源依据：\n  - 依赖：无",
                1,
            )
            text = text.replace(
                "| interface-details/02-interface-01-submit.md | D1 / C1 | T1 | T2 | 提交 |",
                "| interface-details/02-interface-01-submit.md |  | T1 | T2 | 提交 |",
            )
            path.write_text(text, encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        error_text = "\n".join(errors)
        self.assertIn("03-tasks.md T1 详细任务 缺少来源依据", error_text)
        self.assertIn("03-tasks.md 接口映射 行“interface-details/02-interface-01-submit.md” 缺少来源依据", error_text)

    def test_task_breakdown_source_refs_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            path.write_text(build_tasks_doc("D9 / C9"), encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        error_text = "\n".join(errors)
        self.assertIn("03-tasks.md T1 引用了 02-design.md 中不存在的设计ID: D9", error_text)
        self.assertIn("03-tasks.md T1 引用了 01-research.md 中不存在的结论ID: C9", error_text)

    def test_task_breakdown_l0_does_not_require_worker_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            text = build_tasks_doc("D1 / C1")
            text = text.replace("- 并行执行等级：L2", "- 并行执行等级：L0")
            text = text.replace("- 不并行原因（L0 必填）：不适用", "- 不并行原因（L0 必填）：任务集中在同一 Service，串行更清晰")
            text = text.replace("| W1 | T1 | src/main/java/demo/ReportService.java | src/main/resources/application.yml | src/main/java/demo/ReportController.java | - | 1 | mvn test |", "| - | - | - | - | - | - | - | - |")
            path.write_text(text, encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        self.assertNotIn("多 agent", "\n".join(errors))

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
        self.assertFalse(review_flags["alignment_needs_review"])

    def test_task_breakdown_l1_does_not_require_worker_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "03-tasks.md"
            text = build_tasks_doc("D1 / C1")
            text = text.replace("- 并行执行等级：L2", "- 并行执行等级：L1")
            text = text.replace("| W1 | T1 | src/main/java/demo/ReportService.java | src/main/resources/application.yml | src/main/java/demo/ReportController.java | - | 1 | mvn test |", "| - | - | - | - | - | - | - | - |")
            path.write_text(text, encoding="utf-8")

            errors = validate_tasks_doc(path, valid_design_ids={"D1"}, valid_claim_ids={"C1"})

        self.assertNotIn("多 agent", "\n".join(errors))

    def test_task_breakdown_template_examples_do_not_satisfy_traceability(self) -> None:
        errors = validate_tasks_doc(
            ASSET_ROOT / "templates" / "task-breakdown-template.md",
            valid_design_ids={"D1"},
            valid_claim_ids={"C1"},
            schema_exists=True,
        )
        error_text = "\n".join(errors)

        self.assertIn("03-tasks.md 缺少已填写的任务行", error_text)
        self.assertIn("来源依据必须引用 Dxx/Cxx/interface-details/04-schema.sql", error_text)

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
        for token in INTERFACE_DETAIL_REQUIRED_TOKENS:
            self.assertIn(token, text)

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
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            quick_path = repo_root / "ggg" / "quick" / "20260703-示例小需求" / "quick.md"
            self.assertTrue(quick_path.exists())
            self.assertIn("Quick 小需求记录：示例小需求", quick_path.read_text(encoding="utf-8"))
            self.assertFalse((repo_root / "ggg" / "features").exists())
            self.assertFalse((quick_path.parent / "meta.json").exists())
            self.assertIn("不进入 full 需求状态机", completed.stdout)

    def test_to_tasks_requires_valid_design_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            feature_dir = repo_root / "ggg" / "features" / "20260319-示例需求"
            workflow_dir = repo_root / "ggg" / "workflow" / "templates"
            feature_dir.mkdir(parents=True, exist_ok=True)
            workflow_dir.mkdir(parents=True, exist_ok=True)

            for template_name in [
                "baseline-template.md",
                "blocking-issues-template.md",
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
                    "blocking_issues": "01-blocking-issues.md",
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
            (feature_dir / "01-blocking-issues.md").write_text(
                """# 阻塞问题清单

## 2. 阻塞问题

| 编号 | 问题 | 当前卡点 / 需要谁确认 | 是否已确认 |
|---|---|---|---|
| B1 | 主链路已确认 | 无 | 是 |
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


if __name__ == "__main__":
    unittest.main()
