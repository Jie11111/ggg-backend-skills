# 通用文档映射

## 默认目录

```text
ggg/
├─ workflow/
│  ├─ README.md
│  └─ templates/
├─ quick/
│  └─ YYYYMMDD-quick-name/
│     └─ quick.md
└─ features/
   └─ YYYYMMDD-demand-name/
      ├─ meta.json
      ├─ 00-baseline.md
      ├─ 01-research.md
      ├─ 02-design.md
      ├─ interface-details/
      ├─ 03-tasks.md
      ├─ 04-schema.sql
      ├─ 05-implementation-log.md
      ├─ 06-code-review.md
      ├─ review-rounds/
      ├─ 07-test-report.md
      └─ test-rounds/
```

## 命名规则

- 阶段主文档只用固定编号文件名
- 同一阶段只保留一份权威主文档
- 允许的主文档：`00-baseline.md`、`01-blocking-issues.md`、`01-research.md`、`02-design.md`、`03-tasks.md`、`04-schema.sql`、`05-implementation-log.md`、`06-code-review.md`、`07-test-report.md`
- `interface-details/` 只放接口文档，命名为 `02-interface-01-主题.md`
- `review-rounds/` 只放代码检查轮次明细，命名为 `review-rNN.md`
- `test-rounds/` 只放测试验证轮次明细，命名为 `test-rNN.md`
- `quick.md` 只用于 quick 小需求轻量记录，不属于 full 阶段主文档，不进入 `meta.json` 状态机

## 产物职责

| 文档 | 产出阶段 | 职责 |
|---|---|---|
| `ggg/quick/.../quick.md` | quick 需求入口 / 实现 / 按需 review-test | 小需求边界、实现摘要、验证记录和最终结论 |
| `meta.json` | 需求受理 | 状态文件 |
| `00-baseline.md` | 需求受理 | 需求理解、范围、疑问确认 |
| `01-research.md` | 需求对齐 | 代码调研结论、主链路、证据 |
| `02-design.md` | 技术方案 | 技术方案主体 |
| `04-schema.sql` | 技术方案 | SQL 表结构变更（先于 02-design） |
| `interface-details/` | 技术方案 | 单接口详细设计 |
| `03-tasks.md` | 任务拆分 | 可执行的开发任务 |
| `05-implementation-log.md` | 编码实现 | 实际修改文件、文件锁、偏差回写和验证记录 |
| `06-code-review.md` | 代码检查 | Review 轮次索引、当前结论和未关闭问题 |
| `review-rounds/` | 代码检查 | 每轮代码检查明细 |
| `07-test-report.md` | 测试验证 | 测试轮次索引、当前结论和未关闭缺口 |
| `test-rounds/` | 测试验证 | 每轮测试验证明细 |
