# Testcase 基础设施架构优化实施计划

> 日期：2026-07-13  
> 状态：待评审  
> 范围：`D:\code\testcase` 基础设施层  
> 关联契约：Worker 执行内核与任务生命周期契约

## 1. 背景与目标

Worker 与平台后端已经升级任务生命周期、可重复轮询、异步提交幂等和结构化错误。Testcase 工程仍按旧契约处理异步任务，存在重复提交、终态遗漏、固定轮询超时和错误信息丢失等风险。

本次优化目标是让 Testcase 工程完整适配新 Worker 契约，同时整理公共基础设施边界。所有兼容改造位于 `common/`、AW 基类、pytest 基础设施、文档和独立单元测试中，不要求存量测试用例迁移。

## 2. 不可变兼容边界

以下内容属于远端存量用例契约，本次不得修改：

1. 不修改任何真实 `testcases/**/*.py` 文件。
2. 不改变 `testcases/{platform}/{module}/test_*.py` 目录和命名约束。
3. 保持 `@pytest.mark.users({...})` 声明方式不变。
4. 保持 `users["userA"]`、`users["userA_api"]` 取用户方式不变。
5. 保持 `User.__getattr__` 代理 AW 方法的调用方式不变。
6. 保持既有 AW 的 `do_*`、`should_*` 方法名称、位置参数、关键字参数和返回约定不变。
7. 保持 `BaseAW` 已公开原子方法签名不变。
8. 保持 `with parallel(max_workers=..., timeout=...):` 使用方式和公开签名不变。
9. 不修改 OCR 服务、Worker 动作实现、推流协议、`win-control` 和平台前端。

允许在公共方法尾部增加可选参数，但默认行为必须兼容旧调用。

## 3. 当前问题清单

### 3.1 异步请求缺少幂等键

`common/testagent_client.py` 在连接被关闭时会重建 Session 并自动重试一次，但 `execute_async()` 未发送 `Idempotency-Key`。若 Worker 已收到第一次 POST 而响应丢失，客户端重试可能创建第二个任务，造成同一批动作重复执行。

### 3.2 Worker 结构化错误被丢弃

客户端使用 `response.raise_for_status()` 后统一包装字符串异常，无法保留 Worker 返回的：

- `code`
- `message`
- `retryable`
- `details`
- HTTP 状态码
- `request_id`

上层只能通过英文字符串包含关系识别连接错误，判断不稳定。

### 3.3 并发轮询状态机不完整

`common/parallel.py` 当前只明确处理 `success/completed` 和 `failed`。以下状态会一直轮询到本地超时：

- `timeout`
- `cancelled`
- `interrupted`

`accepted`、`cancelling` 虽然会继续轮询，但没有显式契约；未知状态也不会快速失败。

### 3.4 超时语义不一致

`parallel(timeout=300)` 外层允许等待 300 秒，单批轮询内部却固定最多 60 秒，长任务会被提前判定失败。累计 sleep 也没有计入 HTTP 请求耗时。

### 3.5 重试判断逻辑散落

`common/testagent_client.py`、`aw/base_aw.py` 和 `conftest.py` 分别维护连接关闭字符串列表，容易产生行为漂移。

### 3.6 API 文档仍描述旧语义

`api.yaml` 仍写明任务查询后销毁，未描述幂等请求头、新状态、结构化错误和取消中状态。

### 3.7 缺少公共基础设施单元测试

工程当前 pytest 默认收集真实 `testcases/`，缺少不依赖 Worker、设备和业务环境的客户端与状态机单元测试。

## 4. 目标架构

```text
Testcases（调用契约保持不变）
    |
    v
User / AW（业务语义与公开方法保持不变）
    |
    +--> 同步动作 --> TestagentClient --> Worker
    |
    +--> parallel 收集 --> ParallelContext
                              |
                              +--> 幂等异步提交
                              +--> 任务生命周期状态机
                              +--> 可重复结果轮询
                              +--> 结构化失败映射

公共横切能力：
- WorkerError / TestagentError：统一错误模型
- RetryPolicy：只识别传输层可重试错误
- ReportLogger：保留现有报告接口
```

设计原则：

- Testcase 层只表达业务步骤，不感知 Worker 生命周期。
- `TestagentClient` 负责 HTTP 契约、幂等键、响应解析和传输错误分类。
- `ParallelContext` 负责任务状态机和批次结果到 AW 错误的映射。
- AW 基类只消费结构化错误，不重复解析 HTTP 响应。
- 兼容旧 Worker 的字符串 `detail` 和历史 `completed` 状态。

## 5. 详细实施方案

### 5.1 Worker 客户端契约适配

修改：`common/testagent_client.py`

1. `_request()` 增加内部可选 `headers` 参数。
2. 首次请求和连接关闭后的自动重试复用同一份请求头。
3. `execute_async()` 尾部增加可选 `idempotency_key=None`，不影响既有调用。
4. 调用方未传键时，每次逻辑调用生成一个 UUID。
5. 同一次逻辑调用的网络重试复用该 UUID。
6. 两次主动调用即使请求内容相同，也生成不同 UUID，避免错误去重正常重复执行。
7. 不对同步 `/task/execute` 自动重试业务提交，维持当前行为边界。

### 5.2 结构化错误模型

扩展 `TestagentError`，保留 `str(error)` 的旧行为，并增加只读语义字段：

```python
TestagentError(
    message,
    code=None,
    retryable=False,
    details=None,
    status_code=None,
    request_id=None,
)
```

非 2xx 响应解析优先级：

1. FastAPI 新格式 `detail.code/message/retryable/details`。
2. 旧格式字符串 `detail`。
3. 非 JSON 响应正文。
4. HTTP reason 兜底。

客户端本地错误码：

| 场景 | code | retryable |
|---|---|---:|
| 连接超时 | `CONNECTION_TIMEOUT` | true |
| 读取超时 | `READ_TIMEOUT` | true |
| 通用请求超时 | `REQUEST_TIMEOUT` | true |
| 连接中断/重置 | `CONNECTION_ERROR` | true |
| Worker 返回无效 JSON | `INVALID_RESPONSE` | false |

业务错误是否可重试以 Worker 的 `retryable` 为准，不根据 HTTP 状态码自行猜测。

### 5.3 异步生命周期状态机

修改：`common/parallel.py`

状态集合：

```python
SUCCESS_STATUSES = {"success", "completed"}
ACTIVE_STATUSES = {"accepted", "pending", "running", "cancelling"}
FAILURE_STATUSES = {"failed", "timeout", "cancelled", "interrupted"}
```

处理规则：

| 状态 | 行为 |
|---|---|
| `accepted/pending/running/cancelling` | 继续轮询 |
| `success/completed` | 记录动作结果并成功返回 |
| `failed` | 使用失败 action 错误，映射为 `AWError` |
| `timeout` | 立即映射为任务超时错误 |
| `cancelled` | 立即映射为任务已取消错误 |
| `interrupted` | 立即映射为 Worker 中断错误 |
| 空值或未知状态 | 立即报告 Worker 契约错误 |

错误信息优先级：

1. 最后一个失败 action 的 `error`。
2. task 顶层 `error`。
3. 根据终态生成稳定中文消息。

终态没有 action 结果时，错误仍关联当前批次第一个 action，确保 `ParallelExecutionError.errors` 不为空。

### 5.4 超时与轮询语义统一

1. 保持 `parallel(max_workers=10, timeout=300)` 签名不变。
2. 内部每个批次使用同一个 `timeout` 预算，不再固定 60 秒。
3. 使用 `time.monotonic()` 计算截止时间，将 HTTP 查询耗时计入预算。
4. 保持默认 2 秒轮询间隔，定义为模块内部常量。
5. 超时后尝试调用 Worker `DELETE /task/{task_id}` 请求取消，是否实施需在编码前结合现有并发退出行为确认；取消失败不能覆盖原始超时错误。
6. 外层线程池超时与内层批次超时使用相同预算，避免双重且互相矛盾的计时器。

### 5.5 重试策略收口

1. 在 `common/testagent_client.py` 提供 `is_retryable_transport_error(error)`。
2. `aw/base_aw.py` 和 `conftest.py` 优先读取 `TestagentError.code/retryable`。
3. 保留旧连接异常字符串作为 fallback，兼容第三方异常和旧版本异常。
4. 只对传输层连接中断执行现有一次重试。
5. `DEVICE_BUSY` 等业务错误即使 `retryable=true`，本期也不在 AW 内自动重放动作，避免副作用；由任务调度层决定后续策略。

### 5.6 Session 与线程安全

审查确认每个非 API `User` 独立创建一个 `TestagentClient`，不同并发用户不共享 Session。因此本期不引入全局锁或线程本地 Session，避免不必要复杂度。

需要补测试验证：同一客户端在断链重建 Session 时，请求头和幂等键保持一致。

### 5.7 保活、配置和 API AW

本期不改变公开行为：

- `KeepAliveManager` 保持现有启动/停止接口。
- `ConfigLoader` 保持单例和配置读取接口。
- `BaseApiAW` 保持现有 token/session 行为。
- 不重构真实业务 AW。

仅在结构化错误接入确有需要时，做最小范围适配。保活失败观测性、API token 并发锁等作为后续独立议题，不与 Worker 契约改造混合。

## 6. 文件级修改清单

计划修改：

- `common/testagent_client.py`
- `common/parallel.py`
- `aw/base_aw.py`（仅重试错误识别）
- `conftest.py`（仅 Hook 重试错误识别）
- `api.yaml`
- `AGENTS.md`

计划新增：

- `tests/unit/test_testagent_client.py`
- `tests/unit/test_parallel_task_lifecycle.py`
- `tests/architecture/test_testcase_contract.py`

明确不修改：

- `testcases/**/*.py`
- 业务 AW 的公开方法
- 用户配置结构
- pytest marker 使用方式

## 7. 单元测试计划

### 7.1 客户端测试

1. `execute_async()` 自动生成非空幂等键。
2. 两次主动调用生成不同的幂等键。
3. 显式传入幂等键时原样发送。
4. 连接关闭后自动重试复用原幂等键。
5. 连接关闭后只重试一次。
6. 解析结构化 `409 DEVICE_BUSY`。
7. 解析 `409 IDEMPOTENCY_CONFLICT` 及 details。
8. 兼容旧字符串 `detail`。
9. 兼容非 JSON 错误正文。
10. 无效成功 JSON 映射为 `INVALID_RESPONSE`。
11. 连接、读取、通用超时错误码与 retryable 正确。
12. `str(TestagentError)` 仍返回原消息。

### 7.2 生命周期状态机测试

1. `accepted -> pending -> running -> success` 成功。
2. `cancelling -> cancelled` 立即以取消终态结束。
3. `failed` 正确关联失败 action、错误截图和 task_id。
4. `timeout` 没有 action 时仍产生可定位错误。
5. `interrupted` 没有 action 时仍产生可定位错误。
6. 历史 `completed` 状态保持兼容。
7. 未知状态立即失败，不等待完整 timeout。
8. `parallel(timeout=...)` 作为内部轮询预算。
9. 使用单调时钟，HTTP 查询耗时计入超时。
10. 查询结果可重复读取，不依赖一次性消费。

### 7.3 架构契约测试

静态验证：

1. 本次变更不涉及 `testcases/**/*.py`。
2. `parallel()` 的公开签名保持不变。
3. `User.__getattr__` 代理入口存在。
4. `BaseAW` 关键原子方法签名保持基线。
5. `execute_async()` 只在尾部增加可选参数。
6. API 文档不再出现“查询后销毁”的旧描述。

## 8. 测试运行方式

所有 Python 命令使用工程虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest tests/unit tests/architecture -q
```

验证分层：

1. `python -m py_compile`：修改模块语法检查。
2. 独立单元测试：不访问真实 Worker、设备和网络。
3. 架构契约测试：验证远端用例兼容边界。
4. pytest collection：只做用例收集检查，发现导入回归。
5. 真实端到端执行由用户环境验收，不在单元测试中连接设备。

如完整收集依赖业务环境或外部资源，只报告阻塞项，不修改用例绕过。

## 9. 实施顺序

### 阶段 A：建立保护网

1. 新增测试目录和客户端响应模拟工具。
2. 先编写幂等键、结构化错误、状态机和公开签名测试。
3. 确认旧实现下测试按预期失败。

### 阶段 B：客户端契约改造

1. 增加请求头透传。
2. 增加逻辑调用级幂等键。
3. 实现统一响应解析和结构化异常。
4. 运行客户端单元测试。

### 阶段 C：并发执行状态机

1. 引入明确状态集合。
2. 统一终态错误映射。
3. 统一 timeout 和单调时钟。
4. 运行生命周期测试。

### 阶段 D：上层最小适配

1. 收口 `BaseAW` 连接错误识别。
2. 收口 Hook 连接错误识别。
3. 保留字符串 fallback。
4. 运行 AW 与 Hook 相关回归测试。

### 阶段 E：文档和完整验证

1. 更新 `api.yaml`。
2. 更新 `AGENTS.md` 兼容红线。
3. 运行全部新增测试和 collection 检查。
4. 检查 `git diff --check`、`git status` 和 `testcases/` 零改动。

## 10. 验收标准

满足以下条件才算完成：

- 异步自动重试不会创建重复 Worker 任务。
- Worker 新旧错误格式均能被客户端稳定解析。
- 所有 Worker 活跃状态和终态都有明确处理。
- 未知状态不会静默轮询到超时。
- `parallel(timeout)` 与内部轮询预算一致。
- 可重复查询结果不会被客户端当作一次性资源。
- 所有新增单元测试通过。
- pytest 用例收集无新增错误。
- `testcases/**/*.py` 无任何改动。
- 既有 User、AW 和 parallel 调用代码无需修改。
- `api.yaml`、`AGENTS.md` 与实现一致。

## 11. 风险与回滚

### 主要风险

- Worker 不同部署版本返回的错误格式不一致。
- 部分历史 Worker 仍返回 `completed`。
- 任务终态可能没有 action 结果。
- 旧 Hook 依赖特定英文连接错误字符串。
- 长任务将从固定 60 秒转为遵循调用方 timeout，可能暴露过去被提前终止掩盖的问题。

### 控制措施

- 新旧格式双解析。
- 保留 `completed` 和字符串错误 fallback。
- 终态无 action 时仍关联批次 action。
- 改动按客户端、状态机、上层适配分层提交或分层审查。
- 不迁移、不批量格式化、不修改真实用例。

### 回滚边界

所有行为改动集中在公共基础设施文件，可按阶段独立回滚；新增测试和契约文档应保留，用于防止旧的一次性查询和无幂等提交语义再次进入工程。

## 12. 本期明确不做

- 不改测试用例结构和业务调用方法。
- 不批量重构业务 AW。
- 不更换 `requests` 或 pytest 技术栈。
- 不改资源管理平台接口。
- 不引入数据库或本地任务持久化。
- 不在 AW 层自动重试业务动作。
- 不处理 OCR、推流、设备控制或 Worker 安装升级。