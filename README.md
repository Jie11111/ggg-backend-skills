# ggg-backend-skills

一套轻量但可验证的 Java 后端开发 Skills。GGG 会根据需求影响面自动选择：

- `quick`：小改动走最小闭环，保留边界、实现、Review 与验证证据。
- `full`：复杂或高风险需求依次完成需求、调研、设计、拆分、实现、Review 与测试。

## 七个流程阶段

1. `ggg-prd-intake`：受理需求并确定 quick/full。
2. `ggg-requirement-alignment`：核实代码事实、影响面和业务疑问。
3. `ggg-technical-design`：形成可直接实现的技术方案。
4. `ggg-task-breakdown`：拆成有代码落点和完成标准的任务。
5. `ggg-implementation`：按已确认边界实现并冻结完成快照。
6. `ggg-code-review`：基于真实差异完成需求符合性和代码质量检查。
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

需求统一从 `$ggg-prd-intake` 进入。普通表达即可，流程会自动判断 quick/full；只有模式冲突或关键依据不足时才询问。

```text
$ggg-prd-intake
为订单取消接口增加重复请求幂等处理。
```

quick 需求不会机械生成完整文档；full 需求则按七阶段推进，并通过共享状态与差异指纹保证实现、Review、测试结论对应同一份代码快照。
