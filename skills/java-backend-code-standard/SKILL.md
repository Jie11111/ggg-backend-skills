---
name: java-backend-code-standard
description: Java 后端开发与代码评审规范，覆盖注释、链路日志、命名、异常处理、参数校验、MyBatis 使用、事务与返回值约定。Use when 编写、修改、重构、评审 Java Controller/Service/DTO/Mapper 代码，或修复后端质量问题时需要统一标准。
---

# Java Backend Code Standard

## 执行流程

1. 开始编码前，先读取 `references/java-backend-guidelines.md` 对应章节。
2. 编码或评审时，按“强制检查清单”逐项落实。
3. 提交结果前，补齐缺失项；无法满足时明确说明原因和风险。

## 强制检查清单

- 注释：Controller、Service、DTO/VO、枚举、复杂业务逻辑必须有中文注释；TODO/FIXME 必须带责任人和日期。
- 日志：先检查项目根 `pom.xml` 的 `groupId`。若包含 `jzx`，禁止 `log.info` 记录业务流程并使用 `TraceContextUtils.setTraceContextMap` 记录关键链路字段；若不包含 `jzx`，业务流程可使用 `log.info`。两种场景下业务异常都用 `warn`、系统异常都用 `error`，且日志必须带异常对象。
- 命名：类名大驼峰，方法/变量小驼峰，常量全大写下划线；方法名使用约定前缀（get/list/create/update/delete/is 等）。
- 异常处理：区分业务异常与系统异常；禁止吞异常；禁止只打描述不带堆栈。
- 参数校验：Controller 入参使用 `@Valid`；Service 层做空值、范围和业务前置校验。
- MyBatis：避免 N+1 查询；禁止 `SELECT *`；优先明确字段、JOIN、批量操作。
- 通用约束：避免魔法值；严格判空防 NPE；集合返回空集合而非 `null`；事务使用 `@Transactional(rollbackFor = Exception.class)`。
- 语言要求：输出、说明和代码注释使用中文；若项目存在更严格规则，优先遵循项目规则。

## 参考资料

- 详细规范：`references/java-backend-guidelines.md`
