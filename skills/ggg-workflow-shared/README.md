# GGG Workflow Shared

这是 `ggg-*` 需求工作流 skill 的共享底座，不作为独立业务 skill 触发。

它主要提供三类内容：

- `scripts/`
  负责初始化需求目录、推进阶段、同步状态、同步澄清影响、校验文档、扫描仓库输入，以及锁定实现/Review 的 Git 差异指纹
- `references/`
  负责存放文档职责、轻量预检查、写作要点、分轮写法等参考资料
- `assets/workflow/templates/`
  负责存放唯一维护的共享模板，初始化需求目录时会同步到仓库 `ggg/workflow/templates/`

这套共享底座默认服务的真实流程是：

- 接 PRD 或一句话需求
- 先确认 quick 小需求还是 full 正式需求；两者统一落在 `<项目根目录>/ggg/features/YYYYMMDD-需求名/`。quick 用 `quick.md` 记录边界、实现和验证摘要，full 额外初始化 `meta.json` 与阶段文档
- 先分析和找疑点
- 反复澄清并结合代码核验
- 先做技术拆解，再梳理 SQL / 接口 / 枚举 / 依赖
- 最后完成任务拆分、编码实现、代码检查和测试验证闭环

## 实际给项目使用的 README 在哪里

真正会被同步到业务仓库、给程序员直接看的使用手册在：

`assets/workflow/README.md`

初始化需求目录后，它会出现在业务仓库的：

`ggg/workflow/README.md`

## 常用入口

统一命令入口：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" -h
```

快速初始化：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init --repo-root <项目根目录> --feature-name <需求名称>
```

## 维护约定

1. 使用说明优先维护在 `assets/workflow/README.md`
2. 模板变更时，优先检查 README、脚本帮助和校验规则是否一起更新
3. 对外分发时默认安装到 `~/.codex/skills/`，不要在文档里写死具体用户名路径
4. `ggg` 默认保持轻量，不为了 README 再新增额外说明文档
5. `ggg` 是显式阶段工作流：只有用户明确指定阶段 skill 且门禁满足时，才执行阶段推进和文档生成
6. 阶段主文档只允许使用固定编号文件名，不额外生成同阶段重复文档
7. 当前对外流程覆盖：`需求受理 -> 需求对齐 -> 技术方案 -> 任务拆分 -> 编码实现 -> 代码检查 -> 测试验证`；发布、上线、回滚和交付确认不属于 GGG 自动流程
8. `init` 默认只补齐缺失的共享 README 和模板，不覆盖项目里已有的团队定制内容
9. `init-quick` 在统一 `ggg/features` 目录创建 quick 记录，不创建 `meta.json` 或 full 阶段文档；SQL 和接口说明按需使用与 full 相同的 `04-schema.sql`、`interface-details/`
10. 编码前用 `implementation-start` 记录全部 Git 仓库、Txx 范围和 `tiny/normal/high` 风险档位，再用 `implementation-precheck` 锁定该档位的最小实现草图；验证通过 `implementation-verify` 绑定当前代码快照，`implementation-complete` 的豁免只适用于未执行或环境阻塞，不能覆盖已知失败
11. Review 先做 Gate A 需求符合性，再做 Gate B 风险驱动质量检查；新调用由 `review-mark` 显式记录 `fresh-review / self-review`，历史调用未传方式时安全标记为 `self-review`，并绑定实现、权威输入和 Review 工件。可执行测试命令由 `test-run` 生成机器证据；正式门禁继续允许 API/人工观察证据，并绑定完整来源 Manifest、Review 与测试工件
