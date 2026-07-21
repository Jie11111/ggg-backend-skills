# ggg-backend-skills

一套轻量但可验证的 Java 后端开发 Skills。GGG 会根据需求影响面推荐 `quick/full`，最终模式由用户选择：

- `quick`：小改动走最小闭环，保留边界、实现和必要验证证据。
- `full`：复杂或高风险需求依次完成需求、调研、SQL 确认、设计、拆分、实现和测试。

Review 对 quick/full 都是可选动作：只在用户明确要求时检查“代码与需求偏差”和“代码质量与格式”，未执行或发现问题都不会机械阻塞测试。

## 七个流程阶段

1. `ggg-prd-intake`：受理需求并确定 quick/full。
2. `ggg-requirement-alignment`：核实代码事实、影响面和业务疑问。
3. `ggg-technical-design`：形成可直接实现的技术方案。
4. `ggg-task-breakdown`：拆成有代码落点和完成标准的任务。
5. `ggg-implementation`：按已确认边界实现并冻结完成快照。
6. `ggg-code-review`：可选；基于真实差异检查需求偏差、代码质量与格式。
7. `ggg-test-verify`：按风险执行测试并保存可复跑证据。

## 必要共享依赖

以下目录不是额外流程阶段，但七个阶段运行时会使用：

- `ggg-workflow-shared`：状态机、文档模板、校验脚本和回归测试。
- `ggg-java-coding-standard`：implementation 与 code-review 共用的 Java 后端规范。

## 安装

将 `skills` 下的全部目录复制到 Codex skills 目录：

```bash
cp -R skills/* "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Windows PowerShell：

```powershell
Copy-Item -Recurse .\skills\* "$env:USERPROFILE\.codex\skills\"
```

复制后重启或刷新 Codex。

## 使用

需求统一从 `$ggg-prd-intake` 进入。普通表达即可；AI 会先推荐 quick/full 并说明依据，但不会把推荐当成用户的最终选择。

```text
$ggg-prd-intake
为订单取消接口增加重复请求幂等处理。
```

quick 需求不会机械生成完整文档；full 需求在 SQL 语义确认后才进入技术方案。默认不新增测试类；实现完成后可直接进入测试，测试命令使用一次性非 PTY 进程并设置超时。
