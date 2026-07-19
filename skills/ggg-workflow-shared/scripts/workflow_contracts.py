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
    # 仅兼容历史需求目录；新版 GGG 在测试验证通过后结束，不再自动进入此阶段。
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
    # 旧版 full 流程产物，仅为兼容已有需求目录；新版不再创建或读取它。
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
    "## 8. 结论账本（Claim Ledger）",
    "## 9. 进入技术方案前疑问账本",
    "## 10. 残余风险和后续确认方式",
    "## 11. 代码证据索引",
]

RESEARCH_V2_REQUIRED_TOKENS = [
    *RESEARCH_REQUIRED_TOKENS,
    "### 6.1 共享状态、枚举和类型语义影响矩阵",
]

LEGACY_RESEARCH_REQUIRED_TOKENS = [
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
    "## 〇、设计输入覆盖清单",
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

DESIGN_V4_REQUIRED_TOKENS = [
    "## 〇、设计输入去向",
    "## 一、背景与目标",
    "## 二、实例身份与可信边界",
    "## 三、调用方与接口契约",
    "## 四、数据承载设计",
    "## 五、SQL 变更说明",
    "## 六、核心改动",
    "## 七、主链路与依赖",
    "## 十三、设计决策记录",
    "## 十六、测试链路与风险",
]

DESIGN_V5_REQUIRED_TOKENS = [
    *DESIGN_V4_REQUIRED_TOKENS,
    "后端推导字段/来源",
    "禁止外部传字段",
]

INTERFACE_DETAIL_REQUIRED_TOKENS = [
    "## 1. 基本信息",
    "## 2. 契约与参数",
    "## 3. 处理链路",
    "## 4. 测试链路",
]

INTERFACE_DETAIL_V3_REQUIRED_TOKENS = [
    *INTERFACE_DETAIL_REQUIRED_TOKENS,
    "| 契约类型 |",
    "| 契约标识 |",
    "| 调用方 / 触发事件 |",
    "外部是否允许传",
    "- 输出副作用：",
]

TASK_REQUIRED_TOKENS = [
    "## 1. 编码范围",
    "## 2. 拆分方式和执行顺序",
    "## 3. 编码任务",
    "## 4. 任务详情",
    "## 5. 完成定义",
]

TASK_V2_REQUIRED_TOKENS = [
    "## 1. 编码范围",
    "## 2. 拆分依据",
    "## 3. 任务总览",
    "## 4. 任务详情",
    "## 5. 完成定义",
    "- 必要测试代码：",
    "- 最小验证：",
]

IMPLEMENTATION_LOG_REQUIRED_TOKENS = [
    "## 1. 实现记录索引",
    "## 2. 偏差与回写记录",
    "## 3. 验证记录",
    "## 4. 代码质量自检",
    "## 5. 实现会话状态",
]

CODE_REVIEW_INDEX_REQUIRED_TOKENS = [
    "## 1. Review 轮次索引",
    "## 2. 当前结论",
    "## 3. 问题账本（含历史）",
]

CODE_REVIEW_ROUND_REQUIRED_TOKENS = [
    "## 1. 基本信息与输入快照",
    "## 2. 完整 Diff 覆盖",
    "## 3. Gate A：Spec Compliance",
    "## 4. Gate B：Risk-driven Code Quality",
    "## 5. 问题清单",
    "## 6. 历史问题继承与修复闭环",
    "## 7. 评审结论",
]

TEST_REPORT_INDEX_REQUIRED_TOKENS = [
    "## 1. 测试轮次索引",
    "## 2. 当前测试结论",
    "## 3. 缺口账本（含历史）",
]

TEST_REPORT_ROUND_REQUIRED_TOKENS = [
    "## 1. 基本信息",
    "## 2. 测试结论",
    "## 3. 测试依据覆盖",
    "## 4. 测试场景清单",
    "## 5. 执行记录",
    "## 6. 数据影响与恢复",
    "## 7. 缺口和阻塞",
    "## 8. 工件清单",
]

QUICK_RECORD_REQUIRED_TOKENS = [
    "<!-- GGG_QUICK_SCHEMA_VERSION: 2 -->",
    "## 1. 边界确认",
    "- 推进模式：",
    "- 路由依据：",
    "- 代表性验收例：",
    "- 失败 / 重复触发补充：",
    "- 兼容性检查：",
    "| 编号 | 疑问 | 影响级别 | 准确来源 | 为什么不确定 | 用户结论 | 状态 |",
    "## 2. 升级 full 触发条件",
    "## 3. 实现摘要",
    "## 4. 验证记录",
    "## 5. Review / 测试结论",
    "实现会话状态文件",
    "Review 对应实现轮次",
]
