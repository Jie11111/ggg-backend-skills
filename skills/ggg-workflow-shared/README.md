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
- AI 根据范围和风险推荐 quick / full，由用户最终选择；用户也可以明确授权 AI 决定。两者统一落在 `<项目根目录>/ggg/features/YYYYMMDD-需求名/`
- 先分析和找疑点
- 反复澄清并结合代码核验
- 先完成 SQL 影响确认；查询、DML、DDL 或明确无 SQL 都锁定后，才进入技术方案
- 再完成接口设计、任务拆分和编码；默认不创建测试类，同轮处理精度、字段注释、异常、日志和 Trace
- Review 仅在用户明确要求时执行，只检查需求偏差、代码质量和格式；未执行 Review 可直接测试。测试命令使用一次性非 PTY 进程

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
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" init \
  --repo-root <项目根目录> \
  --feature-name <需求名称> \
  --recommended-mode <quick|full> \
  --recommendation-reason "<推荐依据>" \
  --selection-source "<用户选择 full 或授权 AI 决定的消息定位>"
```

## 维护约定

1. 使用说明优先维护在 `assets/workflow/README.md`
2. 模板变更时，优先检查 README、脚本帮助和校验规则是否一起更新
3. 对外分发时默认安装到 `~/.codex/skills/`，不要在文档里写死具体用户名路径
4. `ggg` 默认保持轻量，不为了 README 再新增额外说明文档
5. `ggg` 是显式阶段工作流：只有用户明确指定阶段 skill 且必要前置条件满足时，才执行阶段推进和文档生成
6. 阶段主文档只允许使用固定编号文件名，不额外生成同阶段重复文档
7. 当前对外主流程覆盖：`需求受理 -> 需求对齐 -> 技术方案 -> 任务拆分 -> 编码实现 -> 测试验证`；代码检查由用户按需插入。发布、上线、回滚和交付确认不属于 GGG 自动流程
8. `init` 默认只补齐缺失的共享 README 和模板，不覆盖项目里已有的团队定制内容
9. `init` / `init-quick` 必须记录 AI 推荐及用户最终选择；不允许把 AI 推荐冒充成用户决定。`init-quick` 不创建 `meta.json` 或 full 阶段文档
10. 编码前用 `implementation-start` 记录全部 Git 仓库、Txx 范围和 `tiny/normal/high` 风险档位，再用 `implementation-precheck` 锁定该档位的最小实现草图；验证通过 `implementation-verify` 绑定当前代码快照，`implementation-complete` 的豁免只适用于未执行或环境阻塞，不能覆盖已知失败
11. 新版 full 在需求对齐阶段用 `sql-draft.sql` 和 `confirm-sql` 锁定 SQL 语义；没有 SQL 也要显式登记。历史 `04-schema.sql` / `confirm-schema` 保持兼容
12. Review 完全可选；用户明确要求时只检查代码与需求偏差、代码质量和格式，不区分模式，不作为测试门禁
13. 默认不新增或修改测试类。`test-run` 使用一次性非 PTY 进程，默认 60 秒，超时回收完整进程组；不为脱敏启动常驻终端
