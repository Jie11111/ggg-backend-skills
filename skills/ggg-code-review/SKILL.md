---
name: ggg-code-review
description: 可选的代码检查阶段。仅当用户明确要求 `$ggg-code-review`、Review、检查代码、复查本轮实现或看看还有没有问题时执行；检查代码是否偏离已确认需求，以及代码质量与项目格式是否合格。未被用户选择时不进入 Review，也不影响后续测试。
---

# GGG Code Review

## 定位

只在用户明确要求时检查当前实现。Review 完全可选，不是测试前置门禁；用户没有要求时，不询问是否 Review、不登记跳过状态、不创建 Review 工件，直接按用户要求进入后续验证。

默认只检查不修改。发现问题后报告给用户，由用户决定返回 `$ggg-implementation` 修复，还是继续其他工作。

Review 不分模式，也没有门禁或强制复审轮次。

## 只检查两项

### 1. 代码与需求是否有偏差

对照用户最新确认、PRD、quick 边界或 full 的 baseline/design/tasks，检查：

- 需求要求是否漏实现；
- 已实现行为、接口、SQL、状态、权限或副作用是否与需求不一致；
- 是否加入了需求范围之外的行为。

只记录会影响需求结果的偏差。代码落点或命名不同但行为正确，不算需求偏差。

### 2. 代码质量与格式是否合格

围绕当前真实改动检查：

- 逻辑正确性、空值与边界、异常处理、必要日志和 Trace；
- 接口字段注释、JavaScript 大整数精度、兼容性和明显安全问题；
- 是否存在重复、难维护或明显不符合项目既有写法的代码；
- formatter、lint、import、命名、缩进等项目格式要求。

Java 后端改动读取 `../ggg-java-coding-standard/SKILL.md`，但只应用与本次 diff 直接相关的规则。默认不要求新增测试类。

## 执行流程

1. 确认用户要求 Review，并锁定本次实现 diff 或用户指定范围。
2. 读取最新需求口径、当前 diff 和必要的直接上下游；不重扫无关仓库和历史。
3. 一次完成上面两项检查。默认不运行测试、全量编译、全仓扫描或 formatter，不启动常驻进程；只在某个具体问题必须验证时执行一次有超时的非 PTY 命令。不为 Review 新增测试类。
4. 有问题时优先按严重程度列出 `文件:行号`、问题、影响和建议；没有问题时明确写“未发现需要修改的问题”。
5. 给出 `通过 / 需修改 / 阻塞` 结论。该结论用于告知用户，不作为测试状态机门禁。

Review 超过 60 秒仍未结束时，用一句话说明已检查范围、剩余范围和正在执行的命令；不要重复扫描同一范围。

## 记录方式

Full 仅维护一份 `06-code-review.md`；Quick 仅填写 `quick.md` 的可选 Review 小节。

Full 开始 Review：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" to-review \
  --feature-dir <feature-dir>
```

填写两项检查结果后登记结论：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/ggg-workflow-shared/scripts/workflow_cli.py" review-mark \
  --record <quick.md或05-implementation-log.md> \
  --result <passed|needs_changes|blocked>
```

代码或需求变化后，旧 Review 只作为历史参考；不自动重跑，也不阻止测试。是否再次 Review 仍由用户决定。
