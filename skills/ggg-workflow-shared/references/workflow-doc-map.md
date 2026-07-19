# 通用文档映射

## 默认目录

```text
ggg/
├─ workflow/
│  ├─ README.md
│  └─ templates/
└─ features/
   └─ YYYYMMDD-demand-name/
      ├─ quick.md                 # quick；升级 full 后可保留
      ├─ meta.json                # 仅 full
      ├─ 00-baseline.md           # 仅 full
      ├─ 01-research.md
      ├─ 02-design.md
      ├─ interface-details/       # quick / full 均按需
      ├─ 03-tasks.md
      ├─ 04-schema.sql            # quick / full 均按需
      ├─ 05-implementation-log.md
      ├─ 06-code-review.md
      ├─ review-rounds/
      ├─ 07-test-report.md
      └─ test-rounds/
```

## 命名规则

- 阶段主文档只用固定编号文件名
- 同一阶段只保留一份权威主文档
- 允许的主文档：`00-baseline.md`、`01-research.md`、`02-design.md`、`03-tasks.md`、`04-schema.sql`、`05-implementation-log.md`、`06-code-review.md`、`07-test-report.md`
- 旧需求目录中的 `01-blocking-issues.md` 不再作为账本读取；继续推进前必须把仍有效的问题合并到 `01-research.md` 并删除旧文件
- `interface-details/` 只放接口文档，命名为 `02-interface-01-主题.md`
- `review-rounds/` 只放代码检查轮次明细，命名为 `review-rNN.md`
- `test-rounds/` 只放测试验证轮次明细，命名为 `test-rNN.md`
- `quick.md` 只用于 quick 小需求轻量记录，不属于 full 阶段主文档，不进入 `meta.json` 状态机

## 产物职责

| 文档 | 产出阶段 | 职责 |
|---|---|---|
| `ggg/features/.../quick.md` | quick 需求入口 / 实现 / 按需 review-test | 小需求边界、实现摘要、验证记录和最终结论；Review 优先使用 fresh context，测试按需，不作为默认硬门禁 |
| `meta.json` | 需求受理 | 状态文件 |
| `00-baseline.md` | 需求受理 | 需求理解、范围、疑问确认 |
| `01-research.md` | 需求对齐 | 代码调研结论、主链路、证据 |
| `02-design.md` | 技术方案 | 技术方案主体 |
| `04-schema.sql` | quick 实现 / full 技术方案 | 按需记录 SQL 表结构变更，quick 与 full 文件名一致 |
| `interface-details/` | quick 实现 / full 技术方案 | 按需记录单接口详细设计，quick 与 full 目录和命名一致 |
| `03-tasks.md` | 任务拆分 | 可执行的开发任务 |
| `05-implementation-log.md` | 编码实现 | 任务完成标准证据、实际修改文件、偏差回写、代码质量自检、验证记录和差异指纹 |
| `06-code-review.md` | 代码检查 | Review 轮次索引、当前结论和完整 CRxx 问题账本 |
| `review-rounds/` | 代码检查 | 每轮代码检查明细 |
| `07-test-report.md` | 测试验证 | 测试轮次索引、当前结论和完整 TVxx 缺口账本 |
| `test-rounds/` | 测试验证 | 每轮测试验证明细 |
