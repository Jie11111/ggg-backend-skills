# Java 后端代码规范

## 核心原则

- 可读性优先：代码首先是写给人看的。
- KISS：简单优于复杂。
- DRY：避免重复代码。
- YAGNI：不要过度设计。

## 注释规范

### 必须写注释

| 层级 | 必须注释 |
|------|----------|
| Controller 类/方法 | 类注释、方法注释（接口说明、参数、返回值） |
| Service 类/公共方法 | 类注释、方法注释（参数、返回值、异常） |
| 实体类/DTO/VO | 类注释、字段注释 |
| 枚举类 | 类注释、枚举值注释 |
| Mapper 接口 | 复杂 SQL 方法注释 |
| 复杂业务逻辑 | 行内注释（状态转换、计算公式） |
| TODO/FIXME | 责任人和日期 |

### 注释示例

```java
/**
 * PT 学习记录管理
 *
 * @author zhangsan
 * @since 2026-03-03
 */
@RestController
@RequestMapping("/pt/record")
public class PTRecordController {

    /**
     * 创建 PT 学习记录
     *
     * @param request 创建请求参数
     * @return PT 记录信息
     */
    @PostMapping("/create")
    public Result<PTRecord> create(@Valid @RequestBody CreatePTRecordRequest request) {
        // ...
    }
}
```

```java
// TODO(zhangsan): 2026-03-15 - 需要优化查询性能，考虑添加索引
// FIXME(lisi): 2026-03-10 - 当 userId 为空时会导致 SQL 报错，需要添加参数校验
```

## 日志规范

### 技术选型判定（必须先执行）

- 读取项目根目录 `pom.xml` 的 `<groupId>`。
- 若 `groupId` 包含 `jzx`（不区分大小写），使用 `TraceContextUtils.setTraceContextMap` 作为业务链路日志。
- 若 `groupId` 不包含 `jzx`，业务流程日志使用 `log.info`。
- 无论使用哪种业务流程日志方式，异常日志规则不变：业务异常 `warn`，系统异常 `error`，并打印堆栈。

### 项目日志系统（groupId 包含 jzx 时）

```java
import lombok.CustomLog;
import com.jzx.trace.util.TraceContextUtils;

@CustomLog
public class PTLearningService {
    // 自动注入 log 对象
}
```

### 日志使用原则

| 日志类型 | 使用场景 | 方法 |
|---------|---------|------|
| 链路日志 | `groupId` 包含 `jzx` 时，替代 info 日志，记录业务关键信息 | `TraceContextUtils.setTraceContextMap()` |
| info 日志 | `groupId` 不包含 `jzx` 时，记录业务关键信息 | `log.info("描述, key: {}", value)` |
| error 日志 | 未知异常、系统异常 | `log.error("描述", e)` |
| warn 日志 | 可预知的业务异常 | `log.warn("描述", e)` |

### 业务流程日志要求

- `groupId` 包含 `jzx`：使用链路日志记录关键参数、关键结果、核心状态变化。
- `groupId` 不包含 `jzx`：使用 `log.info` 记录同等级别的关键业务信息。
- 禁止在循环中高频打印日志。
- 禁止输出超大对象，优先输出关键基础字段和值。

### 链路日志附加要求（仅 groupId 包含 jzx）

- 在接口入参处记录关键参数（如 `userId`、`ptId`）。
- 在接口出参处记录关键结果（如 `recordId`、`status`）。
- 在关键业务节点记录状态变更、核心计算结果、外部调用结果。
- 禁止在循环中高频写链路日志。
- 禁止设置整个对象，优先写基础字段和值。

### 异常日志要求

```java
try {
    // 业务逻辑
} catch (BusinessException e) {
    log.warn("业务异常描述, 关键参数: {}", param, e);
    throw e;
} catch (Exception e) {
    log.error("系统异常描述, 关键参数: {}", param, e);
    throw e;
}
```

禁止以下行为：

- 仅用链路日志记录异常，不打印堆栈。
- `log.error("异常描述")` 不传异常对象。
- 吞掉异常不处理。

## 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 类名 | 大驼峰 | `PTLearningService` |
| 方法名 | 小驼峰 | `createPTRecord` |
| 变量名 | 小驼峰 | `userId` |
| 常量 | 全大写下划线 | `MAX_RETRY_COUNT` |

### 方法命名前缀

| 操作 | 前缀 | 示例 |
|------|------|------|
| 查询单个 | get/find | `getUserById` |
| 查询列表 | list/query | `listPTRecords` |
| 新增 | create/insert | `createPTRecord` |
| 修改 | update/modify | `updateZValue` |
| 删除 | delete/remove | `deleteRecord` |
| 判断 | is/has/can | `isCompleted` |

## 异常处理与参数校验

### 异常处理

- 区分业务异常和系统异常。
- 业务异常使用 `warn`，系统异常使用 `error`。
- 所有异常日志必须保留堆栈信息。

### 参数校验

```java
// Service 层：手动校验
public void updateZValue(Long userId, String ptId, Integer zValue) {
    if (userId == null || userId <= 0) {
        throw new IllegalArgumentException("userId 不能为空或小于等于0");
    }
    if (StringUtils.isBlank(ptId)) {
        throw new IllegalArgumentException("ptId 不能为空");
    }
    // ...
}

// Controller 层：@Valid
@PostMapping("/create")
public Result<PTRecord> create(@Valid @RequestBody CreatePTRecordRequest request) {
    return Result.success(ptLearningService.createPTRecord(request));
}
```

## MyBatis 规范

### 避免 N+1 查询

```java
// 错误
List<PTRecord> records = ptRecordMapper.selectByUserId(userId);
for (PTRecord record : records) {
    String ptName = patternMapper.selectNameById(record.getPtId());
}

// 正确
List<PTRecord> records = ptRecordMapper.selectWithPtNameByUserId(userId);
```

### SQL 编写规范

- 禁止 `SELECT *`，必须显式列出字段。
- 优先使用 JOIN 或批量查询减少数据库往返次数。
- 条件必须包含逻辑删除标记等基础过滤条件（如 `is_delete = 0`）。

```xml
<select id="selectWithPtNameByUserId" resultType="PTRecord">
    SELECT r.id, r.user_id, r.pt_id, r.status, p.name AS pt_name
    FROM tob_learning_pt_record r
    LEFT JOIN tower.pattern p ON r.pt_id = p.id
    WHERE r.user_id = #{userId} AND r.is_delete = 0
</select>
```

### 批量操作

```java
// 错误
for (PTRecord record : records) {
    ptRecordMapper.insert(record);
}

// 正确
ptRecordMapper.batchInsert(records);
```

## 其他规范

### 避免魔法值

- 使用枚举或常量代替裸字符串、裸数字。

### 集合/字符串判空

```java
if ("PT001".equals(ptId)) { }
if (StringUtils.isNotBlank(ptId)) { }
if (CollectionUtils.isNotEmpty(records)) { }
```

### 返回值规范

- 集合返回空集合，不返回 `null`。

```java
public List<PTRecord> listPTRecords(Long userId) {
    List<PTRecord> records = ptRecordMapper.selectByUserId(userId);
    return CollectionUtils.isEmpty(records) ? Collections.emptyList() : records;
}
```

### 事务规范

```java
@Transactional(rollbackFor = Exception.class)
public PTRecord createPTRecord(Long userId, String ptId, Long queueId) {
    ptRecordMapper.insert(record);
    queueMapper.updateById(queue);
    return record;
}
```

- 事务注解必须指定 `rollbackFor = Exception.class`。
