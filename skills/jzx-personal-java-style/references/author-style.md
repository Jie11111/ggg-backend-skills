# 作者风格基线

## 适用范围

- 这份 skill 面向 Java 后端项目。
- 目标不是把所有项目都改成公司项目，而是把“作者个人偏好的写法”迁移到不同项目里。
- 公司特有规则只能按“项目已存在才启用”的原则生效，不能反向污染普通项目。

## 先做项目识别

开始编码前，先快速判断下面几件事：

1. 当前项目是否是 Spring MVC / Spring Boot。
2. 当前项目是否已有 `Dubbo`、`MyBatis`、`MyBatis-Plus`、`JPA`、`Feign`、`MapStruct` 等技术栈。
3. 当前项目是否已有这些公司特征：
   - `TraceContextUtils`
   - `ApiResponse` 或同类统一返回体
   - `BaseException` 或同类统一业务异常
   - `EmployeeHelper`、`RequestUser`、`EmployeeApi`
   - `@DubboReference`、`@DubboService`
   - `@CustomLog`
4. 当前模块已经采用什么注入风格、注释语言、日志风格、异常风格。

识别原则：

- 项目已有就沿用。
- 项目没有就不要硬加。
- 通用个人风格可以迁移，基础设施命名不能强绑。

## 通用风格基线

下面这些规则默认适用于公司项目和普通项目。

### 1. 总体取向

- 代码先追求“主链路一眼能看懂”，再追求抽象上的漂亮。
- 能用几个语义明确的方法讲清楚，就不要拆成一堆机械 helper。
- 真复杂的地方允许长一些，但复杂度要落在业务本身，不要落在层级和包装上。
- 优先写显式代码，不要为了“通用性”提前做抽象。
- 如果抽一个方法只是换个名字继续搬运参数，这个方法通常不值得存在。
- 减少无效中间层；不要为了凑 Controller、Service、Facade、Assembler、Manager、Helper 全家桶而分层。

### 2. Controller 风格

- Controller 要薄，职责通常只有 5 件事：接收入参、校验、提上下文、调用 Service、包装返回值。
- 身份上下文在入口提取，例如 `@RequestUser`、`EmployeeHelper.getOid()`、`EmployeeHelper.getEmployeeId()`。
- 如果项目没有现成上下文助手，就用该项目已有的认证上下文获取方式，不要硬套 `EmployeeHelper`。
- 允许在 Controller 做极少量接口边界处理，例如 `String` 转 `Long`、按接口语义组装固定参数。
- 超过接口边界的业务判断，下沉到 Service。
- 如果项目已有统一返回体，就沿用；如果项目没有统一返回体，就遵守项目既有返回风格。
- 不要在 Controller 里堆状态机。
- 新链路优先写短方法，一般一个接口方法就几行。

常见形态：

```java
@RestController
@RequestMapping("/api/xxx")
public class XxxController {

    @PostMapping("/create")
    public Result<XxxResponse> create(@Valid @RequestBody XxxRequest request) {
        Long operatorId = currentUserProvider.getCurrentUserId();
        return Result.success(xxxService.create(request, operatorId));
    }
}
```

如果当前项目已有 `ApiResponse`、`EmployeeHelper`、`@CustomLog`、`@EmployeeApi`，再切回对应写法。

细节偏好：

- 注解顺序尽量稳定，常见是日志、校验、`RestController`、`RequestMapping`、登录态注解。
- 当前文件已经稳定使用 `@Autowired` 时，保持一致即可；不要为了统一风格顺手重写整类。
- 新写独立类时更推荐构造器注入，但不是强制把历史类全改掉。

### 3. Service / Workflow / Facade 风格

- 对外 public 方法先写主步骤骨架，让人快速看到“先做什么，再做什么”。
- 复杂细节拆到私有方法，但私有方法名要表达业务动作，而不是技术动作。
- 优先使用 guard clause 降低嵌套深度。
- 解析、校验、兜底、回填、排序、缓存、通知，通常都拆成独立私有方法。
- 私有方法可以多，但每个都要有清晰业务意图，不能只是把一行代码挪走。

复杂链路的典型写法：

- 主方法表达步骤。
- 关键步骤前用中文注释说明“为什么这样做”。
- 锁、MQ、异步、Redis、延迟任务、事务后通知这类地方必须说明顺序保证和边界。

偏好示例：

- 允许为了外部 Dubbo 链路写一个窄 Facade，不强行污染内部 Service API。
- 如果某个查询只服务单一外部链路，Facade 直接查 Repository 是可以接受的。
- 不要因为“Service 里不能碰 Repository”这类教条，导致内部 API 越抹越厚。

Dubbo 约定：

- 只有项目本身已使用 `Dubbo` 时才应用这组约定。
- 外部依赖使用 `@DubboReference`。
- 对外暴露的实现类使用 `@DubboService`，通常同时保留 `@Service`。
- Facade 负责边界适配，不负责扩散业务复杂度。

事务约定：

- 多表写入、状态变更、通知后置等链路，用 `@Transactional(rollbackFor = Exception.class)`。
- 如果存在“事务提交后再推送/通知”的要求，要显式写注释说明原因。

### 4. Repository / Mapper / SQL 风格

- Repository / DAO / Mapper 保持薄而明确，负责少量空集合保护、返回值整理、底层调用收口。
- 如果项目使用 MyBatis，Mapper 方法名带上核心过滤条件，不写含糊方法名。
- 新 SQL 显式列字段，不要再写 `SELECT *`。
- 查询优先一次拿齐，接受批量查、JOIN、范围查、`UNION ALL` 这类更高效的写法。
- 不要为了分层整洁接受 N+1，不管是查库还是远程调用都一样。
- 基础过滤条件要稳定带上，例如逻辑删除、租户、状态位。
- 集合类查询统一返回空集合，不返回 `null`。

推荐倾向：

- 先判断能不能一次查齐。
- 查不齐时，再考虑缓存、批量补查、上下文预取。
- 不要在循环里逐条查详情、逐条查名称、逐条远程调 Facade。

说明：

- 样本代码里个别历史 SQL 仍有 `SELECT *`；这是历史事实，不是今后要继续沿用的偏好。
- 个人风格的真实方向是“查询明确、字段明确、批量优先、减少回表和往返”。

### 5. 注释风格

- 类注释、对外方法注释、复杂业务块注释必须写中文。
- 如果目标项目已经稳定使用英文注释，跟随项目原有语言，不强行改成中文。
- 注释重点写：
  - 为什么要这样做
  - 顺序为什么不能变
  - 兜底和回填的触发条件
  - 锁、缓存、MQ、事务、状态机的边界
- 不写翻译式废话，例如“给变量赋值”“查询列表数据”这类注释。
- DTO、VO、实体字段如果项目强制要求就写，但优先写业务含义，不写字段名重复翻译。
- TODO、FIXME 要带责任人和日期。

好的注释长这样：

- “事务提交后再广播，避免前端先收到推送、后端事务还没真正落稳。”
- “当前批次按顺序逐条处理，避免同一学生多批 MQ 并发改写 Redis 状态。”
- “缺 questionId 时按最近一次提交思路交互回补，避免切题后补错。”

不好的注释长这样：

- “查询数据”
- “定义变量”
- “循环处理列表”

### 6. 日志、Trace、异常

- 先看项目 `groupId`、依赖和现有代码；只有 `jzx` 项目或已有 `TraceContextUtils` 约定时，才优先 `TraceContextUtils.setTraceContextMap`。
- 其他项目按现有日志风格使用 `log.info` / `log.warn` / `log.error`。
- 不打印整个大对象，优先打印 ID、状态、数量、批次号、时间窗口等关键字段。
- `warn` 用于可预期业务异常、降级、兜底、解析失败。
- `error` 用于系统异常，并保留堆栈。
- 如果项目已有统一业务异常基类，就沿用；没有就遵守项目现有异常体系，不强造 `BaseException`。
- 如果故意降级或吞掉局部异常，必须让代码读者看得出来原因。

推荐记录的字段类型：

- `userId`
- `memberId`
- `oid`
- `employeeId`
- `classroomId`
- `recordId`
- `batchId`
- `trackCount`
- `status`
- `sessionNo`

### 7. 风格禁忌

- 不要为了统一风格重写整文件无关代码。
- 不要为了“以后可能复用”创建一次性 `Util`、`Helper`、`Manager`。
- 不要让 Controller 承担业务判断和状态机。
- 不要让 Service public API 为了单个外部调用越来越臃肿。
- 不要写 `SELECT *`、循环查库、循环远程调用。
- 不要在日志里刷完整 request、response、bizData 大对象。
- 不要把简单问题做成多层抽象；也不要把真正复杂的问题硬压成一个超长方法不解释。

## 公司项目增量约定

下面这些规则只在项目本身已经具备对应设施时启用：

- 已有 `TraceContextUtils`：业务链路优先写 trace 字段，而不是到处堆 `info`。
- 已有 `ApiResponse`：Controller 统一走返回包装。
- 已有 `BaseException` 或错误码枚举：业务校验、权限校验、状态校验优先接入既有异常体系。
- 已有 `EmployeeHelper` / `RequestUser`：上下文在入口提取并显式下传。
- 已有 `Dubbo`：Facade 负责外部边界适配，Service 保持内部业务语义。
- 已有 `@CustomLog`：优先沿用项目统一日志注解。

如果项目没有这些设施：

- 不要新增同名工具类或异常基类来“模拟公司项目”。
- 只迁移通用写法，不迁移公司基础设施命名。

## 样本来源

如果当前环境可访问下面这些样本，可以把它们当作风格参考；访问不到也不影响 skill 使用。

- `D:\towerProject\jzx-tob\poseidon\jzx-tob-learning`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/controller/employee/PublicScreenController.java`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/controller/employee/ReportDownloadTaskController.java`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/controller/employee/SkinManagerController.java`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/controller/employee/VirtualClassroomAlarmController.java`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/controller/employee/VirtualClassroomController.java`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/controller/employee/learningreport/LearningReportManageController.java`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/service/impl/VirtualClassroomAlarmServiceImpl.java`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/service/impl/VirtualClassroomMonitorViewServiceImpl.java`
- `2b/back/org-learn-room-app/src/main/java/com/zstt/tob/learn/room/service/impl/LearningReportManageServiceImpl.java`
- `poseidon/jzx-tob-learning/src/main/java/com/jzx/tob/learning/controller/LearningTrackController.java`
- `poseidon/jzx-tob-learning/src/main/java/com/jzx/tob/learning/service/impl/LearningTrackServiceImpl.java`
- `poseidon/jzx-tob-learning/src/main/java/com/jzx/tob/learning/service/impl/LearningTrackFacadeImpl.java`
- `poseidon/jzx-tob-learning/src/main/java/com/jzx/tob/learning/repository/TrackRepository.java`
- `poseidon/jzx-tob-learning/src/main/resources/mapper/TobLearningTrackMapper.xml`

拿不准时，优先抽样读取与当前任务同层级、同链路、同业务复杂度的文件。

## 拿不准时怎么选

按下面顺序决策：

1. 先看当前文件是否已有稳定写法。
2. 再看同模块、同链路样本。
3. 如果还是有多个可选方案，选更简单、更直接、更少中间层的那个。
4. 如果某种“规范写法”会明显带来 N+1、重复参数搬运、空转抽象，就不要选它。
