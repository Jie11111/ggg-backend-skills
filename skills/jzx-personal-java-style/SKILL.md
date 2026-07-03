---
name: jzx-personal-java-style
description: 按作者偏好的简洁、主链路清晰、少抽象风格编写、修改、重构、评审 Java 后端代码，适用于公司项目和普通 Java 项目。Use when 需要贴近作者既有写法处理 Controller、Service、Facade、Repository、SQL、注释与日志，并根据当前项目是否已有 `TraceContextUtils`、`ApiResponse`、`BaseException`、`Dubbo` 等设施决定是否启用公司特有约定。
---

# JZX Personal Java Style

## 执行方式

1. 如果当前环境可用 `java-backend-code-standard`，先应用它作为基础规范；否则按项目自身基础规范执行。命名、缩进、空格这类通用规则不在这里重复。
2. 先识别当前项目栈与既有约定，再读取 `references/author-style.md` 对应小节。
3. 先执行通用个人风格，再按“项目已存在才启用”的原则补充公司特有约定。
4. 写代码时先服从当前模块、当前文件、当前链路的局部一致性；不要为了套模板把历史代码整片洗风格。
5. 当“通用规范”和“个人风格”冲突时，优先级按下面顺序执行：
   - 项目硬性约束优先。
   - 主链路可读性优先。
   - 简化实现、减少无效抽象优先。

## 快速判断

- Controller 保持薄，只做入参接收、身份上下文提取、少量接口边界解析、调用 Service、按项目约定包装返回值。
- Service、Workflow、复杂链路方法先写主步骤骨架，再把细节下沉到语义化私有方法。
- 只在跨边界时引入 DTO、VO、Facade、Assembler；不要为了“层次完整”增加纯搬运层。
- 优先显式传递 `userId`、`oid`、`employeeId`、`classroomId` 这类上下文，不要在深层方法里反复隐式获取。
- 查询以一次拿齐为目标；优先批量、JOIN、范围查、显式字段，新代码不要再写 `SELECT *`。
- 注释只写业务语义、边界、顺序保证和兜底原因，不写翻译式废话。
- 如果项目已有统一返回封装，就沿用项目返回封装；`ApiResponse.success(...)` 只是公司样本里的常见形式。
- `Dubbo` 只在项目本身已经使用 `Dubbo` 时启用；对外暴露用 `@DubboService`，外部依赖用 `@DubboReference`。
- 只有 `jzx` 项目或已存在 `TraceContextUtils` 约定时，才优先 `TraceContextUtils.setTraceContextMap`；其他项目按既有日志体系处理。

## 风格冲突处理

- 当前文件已经稳定使用字段注入、`@Autowired`、旧注解顺序时，优先保持局部一致，不做无意义清洗。
- 新写的独立类、独立链路，默认优先更简洁的写法，例如构造器注入、薄 Controller、显式上下文参数。
- 历史代码样本里存在不够理想的地方时，不要机械复刻；沿用“作者真实偏好”，例如避免 N+1、避免 `SELECT *`、避免过度分层。
- 当前项目没有 `JZX`、`ZSTT`、`Dubbo`、`MyBatis`、`ApiResponse`、`BaseException` 这些设施时，不要为了套 skill 生造同名基础设施。

## 参考资料

- 详细风格与样本入口：`references/author-style.md`
