#!/usr/bin/env python3
"""GGG 工作流的共享契约定义。"""

from __future__ import annotations

import re


PUBLIC_PHASES = [
    "需求受理",
    "需求对齐",
    "技术方案",
    "任务拆分",
    "编码实现",
    "代码检查",
    "测试验证",
    "交付完成",
]
ALL_PHASES = list(PUBLIC_PHASES)

REVIEW_FLAG_KEYS = [
    "alignment_needs_review",
    "design_needs_review",
    "tasks_needs_review",
]

CANONICAL_STAGE_FILES = {
    "00-baseline.md",
    "01-blocking-issues.md",
    "01-research.md",
    "02-design.md",
    "03-tasks.md",
    "04-schema.sql",
    "05-implementation-log.md",
    "06-code-review.md",
    "07-test-report.md",
}

STAGE_FILE_ALIASES = {
    "baseline.md": "00-baseline.md",
    "research.md": "01-research.md",
    "design.md": "02-design.md",
    "tasks.md": "03-tasks.md",
    "schema.sql": "04-schema.sql",
}

INTERFACE_DETAIL_FILENAME = re.compile(r"^02-interface-\d{2}-.+\.md$")

PLACEHOLDER_TOKENS = [
    "TODO",
    "TBD",
    "待补充",
]

DESIGN_HARD_RESIDUAL_TOKENS = [
    "TODO",
    "TBD",
    "FIXME",
    "待补充",
    "暂定",
    "旧配置名",
    "旧接口口径",
]

DESIGN_RISK_ONLY_TOKENS = [
    "待确认",
    "后续确认",
]

BASELINE_REQUIRED_TOKENS = [
    "## 1. 基本信息",
    "## 2. 需求理解",
    "## 3. 范围边界",
    "## 4. 用户路径与前后端职责",
    "## 5. 业务规则矩阵",
    "## 6. 数据身份矩阵",
    "## 7. 旧链路复用与隔离",
    "## 8. 验收标准",
]

RESEARCH_REQUIRED_TOKENS = [
    "## 1. Baseline 验证清单",
    "## 2. 主链路代码事实",
    "## 3. 旧链路副作用清单",
    "## 4. 数据身份和状态维度对照",
    "## 5. 复用性分级",
    "## 6. 旧能力反向影响检查",
    "## 7. 跨项目依赖能力",
    "## 8. 代码证据覆盖度、运行时证据缺口和置信度",
    "## 9. 结论账本（Claim Ledger）",
    "## 10. 进入技术方案前阻塞问题",
    "## 11. 残余风险和后续确认方式",
    "## 12. 代码证据索引",
]

DESIGN_REQUIRED_TOKENS = [
    "## 一、背景与目标",
    "## 二、实例身份与状态隔离",
    "## 三、前后端接口协作流",
    "## 四、数据承载设计",
    "## 五、SQL 表设计",
    "## 六、核心改动",
    "## 七、主链路与依赖",
    "## 八、接口设计",
    "## 十三、设计决策记录",
    "## 十六、测试链路与风险",
]

INTERFACE_DETAIL_REQUIRED_TOKENS = [
    "## 1. 基本信息",
    "## 2. 契约与参数",
    "## 3. 处理链路",
    "## 4. 测试链路",
]

TASK_REQUIRED_TOKENS = [
    "## 1. 实施概览",
    "## 2. 输入覆盖清单",
    "## 3. 拆分原则、状态和排期顺序",
    "## 4. 任务总览",
    "## 5. 详细任务",
    "## 6. 接口、风险和测试映射",
    "## 8. 完成定义",
]

IMPLEMENTATION_LOG_REQUIRED_TOKENS = [
    "## 1. 实现记录索引",
    "## 2. 文件锁和并行记录",
    "## 3. 偏差与回写记录",
    "## 4. 验证记录",
]

CODE_REVIEW_INDEX_REQUIRED_TOKENS = [
    "## 1. Review 轮次索引",
    "## 2. 当前结论",
    "## 3. 未关闭问题",
]

CODE_REVIEW_ROUND_REQUIRED_TOKENS = [
    "## 1. 基本信息",
    "## 2. 评审结论",
    "## 3. 问题清单",
    "## 4. 一致性复核",
    "## 5. 幻觉审计",
    "## 6. 修复闭环",
]

TEST_REPORT_INDEX_REQUIRED_TOKENS = [
    "## 1. 测试轮次索引",
    "## 2. 当前测试结论",
    "## 3. 未关闭缺口",
]

TEST_REPORT_ROUND_REQUIRED_TOKENS = [
    "## 1. 基本信息",
    "## 2. 测试结论",
    "## 3. 应测场景清单",
    "## 4. 执行记录",
    "## 5. 缺口和阻塞",
]

QUICK_RECORD_REQUIRED_TOKENS = [
    "## 1. 边界确认",
    "## 2. 升级 full 触发条件",
    "## 3. 实现摘要",
    "## 4. 验证记录",
    "## 5. Review / 测试结论",
]
