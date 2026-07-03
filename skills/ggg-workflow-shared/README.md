# GGG Workflow Shared

这是 `ggg-*` 需求工作流 skill 的共享底座，不作为独立业务 skill 触发。

它主要提供三类内容：

- `scripts/`
  负责初始化需求目录、推进阶段、同步状态、同步澄清影响、校验文档、扫描仓库输入
- `references/`
  负责存放文档职责、轻量预检查、写作要点、分轮写法等参考资料
- `assets/workflow/templates/`
  负责存放唯一维护的共享模板，初始化需求目录时会同步到仓库 `ggg/workflow/templates/`

这套共享底座默认服务的真实流程是：

- 接 PRD 或一句话需求
- 先确认 quick 小需求还是 full 正式需求；quick 只在主项目仓库根目录创建 `ggg/quick/.../quick.md` 记录边界、实现和验证摘要后进入实现，full 才初始化完整需求目录
- 先分析和找疑点
- 反复澄清并结合代码核验
- 先做技术拆解，再梳理 SQL / 接口 / 枚举 / 依赖
- 最后完成任务拆分、编码实现、代码检查、测试验证和交付状态闭环

## 实际给项目使用的 README 在哪里

真正会被同步到业务仓库、给程序员直接看的使用手册在：

`assets/workflow/README.md`

初始化需求目录后，它会出现在业务仓库的：

`ggg/workflow/README.md`

## 常用入口

统一命令入口：

```bash
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py -h
```

快速初始化：

```bash
py ~/.codex/skills/ggg-workflow-shared/scripts/workflow_cli.py init --repo-root <主项目仓库根目录> --feature-name <需求名称>
```

## 维护约定

1. 使用说明优先维护在 `assets/workflow/README.md`
2. 模板变更时，优先检查 README、脚本帮助和校验规则是否一起更新
3. 对外分发时默认安装到 `~/.codex/skills/`，不要在文档里写死具体用户名路径
4. `ggg` 默认保持轻量，不为了 README 再新增额外说明文档
5. `ggg` 是显式阶段工作流：只有用户明确指定阶段 skill 且门禁满足时，才执行阶段推进和文档生成
6. 阶段主文档只允许使用固定编号文件名，不额外生成同阶段重复文档
7. 当前对外流程覆盖：`需求受理 -> 需求对齐 -> 技术方案 -> 任务拆分 -> 编码实现 -> 代码检查 -> 测试验证 -> 交付完成`
8. `init` 默认只补齐缺失的共享 README 和模板，不覆盖项目里已有的团队定制内容
9. `init-quick` 只创建 quick 记录，不创建 `ggg/features`、`meta.json` 或 full 阶段文档
