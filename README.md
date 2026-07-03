# GGG Backend Skills

这是一套面向 Java 后端开发的 Codex Skills 工作流。

核心目标：把后端需求分成两种处理方式：

- `quick` 小需求：少文档，快速确认边界后实现和验证。
- `full` 正式需求：完整走需求受理、需求对齐、方案、任务、实现、Review、测试。

当前版本不包含 `ggg-bug-fix`。

## 包含内容

核心流程：

- `ggg-prd-intake`
- `ggg-requirement-alignment`
- `ggg-technical-design`
- `ggg-task-breakdown`
- `ggg-implementation`
- `ggg-code-review`
- `ggg-test-verify`

共享底座：

- `ggg-workflow-shared`

配套规范：

- `java-backend-code-standard`
- `jzx-personal-java-style`

## 安装

把 `skills` 目录下的 skill 复制到本机 Codex skills 目录：

```powershell
Copy-Item -Recurse .\skills\* "$env:USERPROFILE\.codex\skills\"
```

如果你的 `CODEX_HOME` 不是默认目录，就复制到：

```text
<CODEX_HOME>\skills
```

复制后重启或刷新 Codex，让 skills 重新加载。

## quick 小需求流程

适合小改动、快速实现，但仍需要记录边界和验证结论。

```text
$ggg-prd-intake
这是一个小需求：......
我希望按 quick 快速改。
```

流程：

1. `$ggg-prd-intake`：确认 quick/full，创建 `ggg/quick/.../quick.md`
2. `$ggg-implementation`：读取 `quick.md`，定位代码、最小实现、自检和局部验证
3. `$ggg-code-review`：按需复查 quick 改动
4. `$ggg-test-verify`：按需验证 quick 改动

quick 不创建 `meta.json`，不进入完整 `00-07` 文档状态机。

## full 正式需求流程

适合正式需求、影响面较大、涉及接口 / SQL / 状态 / 跨项目 / 旧链路风险的需求。

```text
$ggg-prd-intake
这是 PRD/需求描述：......
请按 full 完整流程推进。
```

流程：

1. `$ggg-prd-intake`：需求受理，输出 `meta.json`、`00-baseline.md`
2. `$ggg-requirement-alignment`：代码事实对齐，输出 `01-research.md`
3. `$ggg-technical-design`：技术方案，输出 `02-design.md`，按需 `04-schema.sql`、`interface-details/`
4. `$ggg-task-breakdown`：任务拆分，输出 `03-tasks.md`
5. `$ggg-implementation`：编码实现，输出代码改动和 `05-implementation-log.md`
6. `$ggg-code-review`：代码检查，输出 `06-code-review.md` 和 review 轮次
7. `$ggg-test-verify`：测试验证，输出 `07-test-report.md` 和测试轮次

## 使用原则

- 所有需求先走 `$ggg-prd-intake`。
- 用户没说 quick/full 时，先问用户选择。
- 用户选择 quick 时，不按 SQL、接口、跨项目机械拒绝，但要提示风险。
- quick 过程中发现影响面不清时，建议升级 full。
- full 流程每个阶段只做当前阶段的事，不提前生成后续文档。
