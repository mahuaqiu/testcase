# parallel() 并行执行重构设计

- 日期：2026-10-23
- 状态：已实施
- 影响范围：`common/parallel.py`、`aw/base_aw.py`、`tests/unit/`；报告、conftest、AW 业务代码、用例层零改动

## 一、背景与问题

### 现有机制

`with parallel():` 开启线程本地收集模式：

1. 块内 AW 业务方法（`do_*`/`should_*`）的 Python 代码**立即执行**；
2. 其中的原子操作（`ocr_click` 等）不真正执行，`action_data` 被收集进队列并返回 `PendingResult`；
3. 退出时按 (user_id, platform, client) 分组，每用户一个批量任务经 `execute_async` 提交 Worker，轮询 `get_task` 汇总结果。

### 根因缺陷

收集模式与 Python 控制流存在**时间线错位**：业务方法的 Python 逻辑在收集期立即执行，原子操作延迟到块退出后执行。由此产生：

| # | 缺陷 | 表现 |
|---|------|------|
| 1 | 取值类操作被禁 | `ocr_exist`/`ocr_get_text`/`ocr_get_position`/`ocr_check_same_row_*` 在块内返回 `PendingResult`，使用即抛 `ParallelModeError`。AW 方法只要含 `if self.ocr_exist(...)` 或取文本逻辑，整个方法无法进并行块 |
| 2 | Python 控制失效 | 依赖执行期状态的 if/for/try 在收集期就定分支，靠报错拦截 |
| 3 | API 用户伪并行 | `BaseApiAW` 无收集模式支持，块内 API 调用同步顺序执行，UI 用户动作之后才批量提交 |
| 4 | 嵌套不支持 | 内层 `parallel()` 退出会关闭外层收集模式 |
| 5 | 错误时序不一致 | 块内 Python 异常立即抛，原子操作失败延后以 `ParallelExecutionError` 抛 |
| 6 | 失败定位粗糙 | 批量任务失败只能映射到"最后一个 action"，报告失败步骤定位不准 |

## 二、目标与非目标

### 目标

1. **核心目标**：含取值/分支/循环/异常处理逻辑的 AW 方法可在不同用户、不同设备间真正并行
2. 顺带解决：API 用户伪并行（API 调用与其余用户并发）
3. 兼容约束：
   - `with parallel()` 语法与调用方式不变，**存量用例零改动**
   - HTML 报告的格式、样式、步骤分组结构**完全不变**
   - `ParallelExecutionError` 异常结构保持
   - 别的在用仓库直接升级本框架代码即可，无迁移动作

### 非目标

1. 同一用户内多调用并发执行（保持顺序，已确认可接受）
2. 并行块内顶层调用的返回值可在块内消费（天然不可行，保持禁止但报错指引清晰）
3. 跨用户数据依赖的声明式表达（A 的结果作 B 的输入仍需分两个 parallel 块或块外顺序执行）
4. Worker（testagent 工程）接口改造——主场景（不同用户不同设备）不需要

## 三、方案选型

| 方案 | 结论 | 理由 |
|------|------|------|
| **A. 客户端线程级真并行** | **采纳** | 根除时间线错位；任意 AW 可并行；改动集中在 2 个文件；报告零改动 |
| B. Worker 端编排 DSL | 否决 | AW 表达力受限子集、开发量大、与"存量用例少改"冲突 |
| C. 收集模式 + Future 化 | 否决 | 分支依赖运行时值仍无解，复杂度花在补丁上 |

## 四、详细设计

### 4.1 CallTask（替代 Action）

```python
@dataclass
class CallTask:
    fn: Callable[[], Any]                       # 闭包：线程内同步执行的真实调用
    user_id: str = ""                           # 以下元数据保留现有字段名，
    platform: str = ""                          # 供 ParallelActionError.action 消费
    aw_name: str = ""
    method: str = ""
    client: Optional["TestagentClient"] = None
```

### 4.2 两个拦截点（`aw/base_aw.py`）

**拦截点 1：业务方法装饰器 `_auto_log_aw_call`**（覆盖所有 `do_*`/`should_*`，含 API AW——继承自动生效）

收集模式下不执行 Python 逻辑，入队闭包并返回 `PendingCall`：

```python
if is_collecting():
    queue = get_action_queue()
    if queue is not None:
        queue.append(CallTask(
            fn=lambda: func(self, *args, **kwargs), ...))
        return PendingCall(f"{self._aw_name}.{func.__name__}")
```

压栈、日志、截图等装饰器逻辑**不执行**——它们在线程内真正调用时按现有同步路径执行。

**拦截点 2：原子操作执行层 `_execute_with_log` / `_execute_exist_check`**

兼容 `with parallel(): userA.ocr_click(...)` 直接调原子操作的写法。将同步执行路径提取为 `_execute_sync()`，收集模式下：

```python
queue.append(CallTask(fn=lambda: self._execute_sync(...), ...))
return None    # 由 _exec 包装为 PendingCall
```

原子操作方法体内的参数构建（`_build_window`、`_ocr_params` 等）为纯本地计算，收集期立即执行无害。

### 4.3 执行模型（`ParallelContext.__exit__`）

```
退出 with parallel():
  1. 关闭收集模式
  2. CallTask 按 (user_id, id(client)) 分组，组内按声明顺序
  3. ThreadPoolExecutor(max_workers)，每执行组一个线程任务：
       a. set_collecting(False)                    # 防御状态泄漏
       b. ReportLogger.set_current(主线程 logger)   # 日志写入同一份报告
       c. 顺序执行组内 CallTask.fn()：
            - 每个 CallTask 执行前检查 deadline，超时跳过组内剩余并记录
            - 完整走现有同步路径（日志、失败截图、request_id 透传）
            - 首个异常中止该组后续 CallTask
  4. 主线程按共享 deadline 等待所有组
  5. 汇总各组首个异常 → ParallelExecutionError(errors)
```

每线程一个执行组的原因：同用户调用链存在隐式状态依赖（登录→验证）需顺序执行；不同用户的 AW 实例、`TestagentClient`、`requests.Session` 天然隔离无共享竞争；业务调用栈为 threading.local，每线程独立 → `parent_call_id` 报告分组天然正确。

### 4.4 失败语义

以"两个用户各 5 步、A 在第 3 步失败"为例：

- A 组：步骤 1、2 成功日志入报告，步骤 3 失败（自动失败瞬间截图、request_id），步骤 4、5 不执行
- B 组：不受影响，完整执行 5 步
- 所有组结束后抛 `ParallelExecutionError`，`e.errors[0].action` 精确指向失败用户与失败原子操作（`user_id`/`aw_name`/`method`），`original_error` 为原始 `AWError`——失败定位比现状批量模式更精确
- 失败不打断其它用户，与现状一致

### 4.5 对外 API 兼容

| 项 | 处理 |
|----|------|
| `parallel(max_workers=10, timeout=300)` | 签名、语义不变 |
| `ParallelExecutionError.errors` / `ParallelActionError` | 结构不变 |
| `is_collecting()` | 保留，含义不变（仍在收集模式中） |
| `PendingResult` / `ParallelModeError` | 类定义保留（存量 import 不报错），框架不再抛出 |
| `PendingCall`（新增） | 块内顶层调用返回值被消费（bool/str/iter/getitem）时抛带指引异常：将取值移到块外 |
| HTML 报告 | 零改动——并行块内日志走与顺序执行完全相同的代码路径，分组靠 `parent_call_id` |
| `TestagentClient.execute_async/get_task/cancel_task` | 保留（Worker 接口仍在，parallel 路径不再使用） |

### 4.6 超时（默认 300s 统一预算）

- 主线程按 deadline 等待，超时组记 `TimeoutError` 进 errors
- 线程内每个 CallTask 执行前检查 deadline，超时跳过组内剩余
- **超时传导（关键设计）**：每个同步 `/task/execute` 请求携带 `config={"timeout": 剩余预算ms}`。`TestagentClient.execute` 的 `config` 参数通路已存在，Worker 端 `TaskConfig.timeout` 会把正在执行 action 的 `action_deadline` 收紧到任务 deadline（`ExecutionControl.checkpoint()` 处抛超时）、后续 action 不执行，任务以 TIMEOUT 终态返回——**用现有 Worker 能力实现与现状 `cancel_task` 等价的中断精度，Worker 零改动**
- **HTTP read_timeout 协调**：执行请求的 read_timeout（默认 125s）需覆盖剩余预算（取 `max(125s, 剩余预算+15s缓冲)`），避免客户端先于 Worker 断连产生孤儿任务
- 残留差距：超时瞬间未到达自身 checkpoint 的 action 需等其 checkpoint/自身 timeout——与现状 cancel 的实际语义一致（现状 cancel 也是 checkpoint 响应，且客户端发完 cancel 不等确认即抛错）

### 4.7 嵌套 parallel

外层收集模式下内层 `parallel()` 的块体属于被延迟的 Python 逻辑，实际不会在收集期执行；AW 方法内部若使用 `parallel()`，运行于该用户的执行线程中，threading.local 状态独立，天然正确。

## 五、性能特征

- 每原子操作一次同步 `/task/execute`（不再批量），往返开销几十 ms，相比 OCR/图像操作秒级耗时可忽略
- 省去 2s 间隔轮询的发现延迟（现状任务完成后平均多等 ~1s），总耗时基本持平或略优
- 主场景（不同用户不同设备）请求分散在不同 Worker，单 Worker 压力不变
- 所有用户第一个操作由线程同时发起，"同时登录/同时入会"启动同时性与现状等价

## 六、测试策略

### 单元测试（重写 `tests/unit/test_parallel_task_lifecycle.py` → `tests/unit/test_parallel_execution.py`）

1. 分组与顺序：同用户多 CallTask 同线程按声明顺序；不同用户并发（事件屏障验证交叠）
2. 任意 AW 可并行：含 `if self.ocr_exist(...)` / `ocr_get_text()` 取值分支的 AW 在块内正确延迟执行，分支按执行期结果走（mock client）
3. 失败语义：A 第 3 步失败 → A 组剩余跳过、B 组完整执行、`ParallelExecutionError` 携带精确 `action.method` 与 `original_error`
4. PendingCall 保护：块内消费顶层返回值抛指引异常
5. 超时：deadline 后剩余 CallTask 跳过并记 TimeoutError
6. logger 注入：子线程日志进入主线程报告实例
7. API AW：块内 API 调用延迟、线程内并发执行（伪并行修复回归）

### 架构契约测试（`tests/architecture/test_testcase_contract.py` 补充）

- `base_aw.py` 不存在 `PendingResult` 抛出路径
- `common.parallel` 对外面（`parallel`/`is_collecting`/`ParallelExecutionError`）签名稳定

## 七、实施顺序

1. `common/parallel.py` 重写：CallTask + 分组线程执行 + logger 注入 + 异常汇总（删除批量任务生命周期逻辑约 250 行）
2. `aw/base_aw.py`：两个拦截点改造、提取 `_execute_sync`、删除 `PendingResult` 抛出路径
3. 单测重写 + 架构契约测试
4. `AGENTS.md` 第六章重写：删旧限制（"验证不应在并行块内"等），新增唯一禁止点（块内顶层调用返回值不可用）

## 八、Worker 并发模型（已核实）与风险

### Worker 并发能力（源码核实，autotest 工程）

- FastAPI 实现；`/task/execute` 为 async 路由，内部 `asyncio.to_thread(worker.execute_sync, ...)` 派发，不阻塞事件循环
- `execute_sync` 内部复用异步路径：`submit_async` 提交到 `TaskService._executor`（ThreadPoolExecutor, max_workers=16）后阻塞等 Future——同步/异步走**同一执行与租约模型**
- 409 DEVICE_BUSY 来源为 `ResourceScheduler` 租约，粒度（`worker/task/service.py::_resource_key_for_task`）：

| 平台 | 租约粒度 | 同 Worker 并行能力 |
|------|----------|--------------------|
| windows / mac（Worker 本机，DESKTOP_PLATFORMS） | `platform:{platform}`（共享物理键鼠） | 同平台任务互斥 |
| ios / android / harmony_pc / harmony_mobile（带 device_id） | `device:{platform}:{sn}` | **不同设备互不冲突，真并行** |
| 纯 cmd_exec | 设备级命令锁 | 不同设备互不冲突 |

- **结论**：一台 Windows Worker 连三台鸿蒙 PC/手机，三台设备三个独立租约 + 16 线程池，并行完全支持，Worker 零改动
- **409 行为与现状等价**：同步/异步走同一租约模型，新方案不引入新的冲突面；仅"同一 Worker 同平台（windows/mac/web）多用户"会冲突——该场景现状同样 409，通常资源分配上每桌面/web 用户对应独立 Worker

### cmd_exec 轮询类 AW 的行为（用户场景核实）

"AW 异步调用 cmd_exec 命令 + 循环查询结果"（如 `background=True` 启动采集后 `while` 轮询状态）：

- **不阻塞其它用户**：整个方法为所属用户线程内的一个 CallTask，其它用户独立线程
- **超时行为与现状等价且粒度更细**：每次查询为独立 execute，带剩余预算传导（4.6）；单次查询另有 cmd_exec 自身 timeout（默认 30s）兜底。外部命令一直不完成时，剩余预算耗尽 → 该次查询被 Worker 以 TIMEOUT 终止 → 循环中断 → 仅该组记 TimeoutError。需要更长时间时调大 `parallel(timeout=...)`，与现状一致
- **租约持有粒度变化**：现状启动+全部轮询在一个批量任务内同命令域全程独占；新方案两次查询之间命令锁释放，同域任务可在间隙插入——对轮询场景通常更好（不无谓独占），实际影响面小（同用户线程内顺序执行；跨用户设备/账号本就隔离）
- **background 命令存活**：Worker 端拉起的后台进程不随任务结束而终止，与现状一致
- **现状缺陷顺带修复**：Worker 约束纯 `cmd_exec` 任务走命令锁、禁止与平台 action 混在同一任务（`INVALID_TASK_ACTIONS` 400）。现状收集模式把同用户所有 action 混进一个批量任务——方法内 cmd_exec 与 ocr_click 交替的 AW 在并行块内会整批 400；新方案每操作独立请求，天然规避

### 风险

| 风险 | 缓解 |
|------|------|
| 同 Worker 同平台多用户（如两个 web 用户）409 | 已确认上层不会对 Worker 本机（windows/mac）发起并行任务，并行仅发生在 Worker 本机与 SN 设备之间（不同资源域），该场景实际不存在；保留客户端 409 重试作为防御性兜底 |
| 超时不可中断正在执行的操作 | 通过 `config.timeout` 传导剩余预算（见 4.6），中断精度与现状 cancel 等价；OCR 自带 timeout 兜底 |
| 存量用例依赖批量模式的隐性行为（如失败截图时序） | 日志/截图走同步路径与顺序执行一致，风险低；上线后回归存量关键用例 |
