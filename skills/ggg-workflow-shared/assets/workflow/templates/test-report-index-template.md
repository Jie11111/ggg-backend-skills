# 测试报告索引

> 每次 formal-gate 新增 `test-rounds/test-rNN.md`，不得覆盖历史。`run-only`、`triage` 可以生成明细，但不能把局部结果登记为阶段通过。原始证据保存在 `reports/test-evidence/`，接口专项证据保存在 `reports/api-tests/`；测试工件指纹只由 `test-mark` 写入 `implementation-state.json`。

## 1. 测试轮次索引

| 轮次 | 时间 | 模式 | 结论 | 对应实现 | 明细文档 | 关联接口报告 | 未关闭缺口 |
|---|---|---|---|---|---|---|---|
| T1 |  | formal-gate / run-only / triage | 通过 / 需补测 / 阻塞 / 局部观察 / 已定位 | I1 | test-rounds/test-r01.md | 不涉及 / reports/api-tests/xxx.md | 无 / TV1 |

## 2. 当前测试结论

- 最新轮次：
- 当前模式：
- 当前结论：
- 测试阶段是否完成：
- 对应实现轮次与差异指纹：
- Review 输入：未执行 / 可选参考 `06-code-review.md`
- 需要回到实现的问题：
- 剩余风险：

## 3. 缺口账本（含历史）

> 保留历轮全部 TVxx，并在新轮次继承尚未关闭项。编号不可删除或重用；`fixed / accepted / not-applicable` 必须有关闭轮次与证据。

| 缺口编号 | 首次轮次 | 最近轮次 | 缺口 | 主要归因 | 当前状态 | 关闭轮次/证据 | 后续处理与复验条件 |
|---|---|---|---|---|---|---|---|
| TVxx | Txx | Txx |  | 需求歧义 / 方案遗漏 / 实现偏差 / 测试用例偏差 / 环境或数据问题 / 覆盖不足 | open / fixed / accepted / not-applicable |  |  |
