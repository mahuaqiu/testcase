# 伴生平台设计（`web+windows`）

- 日期：2026-11-13
- 状态：已评审通过
- 关联：AGENTS.md 五（用户资源管理）、conftest.py（users fixture）

## 1. 背景与目标

同一账号可能同时操作 web 端与 windows 端（web 为主操作端，windows 为伴生验证端）。
两端跑在**同一台执行机、同一个 worker 端口**上，共用账号资源。

目标：

1. 用例层用单一标记声明主平台 + 伴生平台：`@pytest.mark.users({"userA": "web+windows"})`
2. 现有写法 `@pytest.mark.users({"userA": "web"})` 行为完全不变
3. 用例内取用户：
   - `users["userA"]` → web 端 User
   - `users["userA_windows"]` → windows 端 User（同账号）
   - `users["userA_api"]` → API 端 User（同账号，现状不变）
4. 资源平台交互不变：**申请、释放、keepalive 只针对主平台（web）一台机器**

非目标：

- 不支持多伴生（`web+windows+mac`）与伴生的伴生
- 不生成 `userA_windows_api`（`userA_api` 已覆盖同账号 API 操作）
- 不改动 UserManager 与资源平台 API 的契约

## 2. 标记语法与解析

- 通用规则：`"{主平台}+{伴生平台}"`，单一伴生，伴生平台名即实例后缀
- 多用户可各自声明：`{"userA": "web+windows", "userB": "web"}` → 仅 userA 有伴生
- 解析产物（在 `users` fixture 内完成，抽为 `common` 可单测的纯函数）：
  - 平台申请体：`{"userA": "web"}`
  - 伴生映射：`{userA: "windows"}`
- 申请前校验（失败 `pytest.fail`，不发起申请）：
  - 主平台不能是 `api`
  - 伴生平台必须存在对应 AW 目录（`aw/{platform}/`）
- 防歧义：marker 同时显式声明 `userA_windows` 键、userA 又声明伴生 → 报错；
  未声明伴生时 `{"userA_windows": "windows"}` 仍是普通独立用户（向后兼容）

## 3. 资源申请 / 释放 / keepalive

- 申请体只含主平台 → 响应解析、release、keepusing 天然只有 web 机器 ID，
  UserManager 零改动
- fixture keepalive 循环增加 `if user_id not in raw_resources: continue`，
  伴生用户不创建空保活线程
- mock 模式（base_url 为空）：同样只按主平台 key 取 mock 资源，
  伴生用户由同一 mock 资源合成

## 4. 用户实例

| key | platform | 资源来源 | 说明 |
|-----|----------|----------|------|
| `userA` | web | 平台申请 | 不变 |
| `userA_windows` | windows | 复用 userA 资源 | 同 ip/port/account/password/name/extra，加载 windows AW，走同一 worker |
| `userA_api` | api | 复用 userA 资源 | 不变 |

- 主/伴生是两个独立 `User` 实例、两个独立 `TestagentClient`（同地址），互不串状态
- 伴生 User 参与现有 `validate_user_keys`、`app_type` 解析、teardown 排序
  （api 优先 → 其它按声明顺序）

## 5. hooks —— 伴生懒触发

- hooks 解析链不变：config.yaml 平台默认 → 目录 conftest 层 → 用例标记
  （用例可用 `userA_windows` 用户键覆盖）；`app_type` 照常挂 User 属性
- 主平台用户（userA）：setup hooks 照旧在测试体前执行
- 伴生用户（userA_windows）：
  - **setup hooks 延迟到该用户首次通过 `__getattr__` 取到 AW 方法时执行，
    执行后清空**（懒触发）
  - teardown 沿用现有 `_used` 门槛
  - 用例完全没用伴生用户 → setup/teardown 都不执行，windows 客户端全程不拉起
- 实现机制：fixture 不直接执行伴生 setup，把 setup hooks 与执行回调
  （复用 `_execute_hooks` 的重试/日志逻辑）挂到 User 待执行槽；
  `User.__getattr__` 返回可调用属性前先触发并清空
- 懒执行失败：异常从用例调用点抛出，按 AW 失败记录（`log_error` 带 user_id），
  用例失败归属该伴生用户

## 6. 报告与失败截图

- 失败补充截图：**伴生用户一律跳过** —— 与主用户同一台机器，
  主用户（web, system 级）截图已覆盖同一桌面；
  失败 AW 调用自带的 `error_screenshot`（归属实际失败用户）保留不动
- 报告 user_details：未使用的伴生用户不写入（与 api 用户同策略）；
  使用过的正常展示 `platform=windows`

## 7. 兼容性与错误处理

| 场景 | 行为 |
|------|------|
| `{"userA": "web"}` | 现状不变 |
| `{"userA_windows": "windows"}`（无伴生声明） | 普通独立用户，现状不变 |
| 伴生平台无 AW 目录 / 主平台为 api / 键冲突 | 申请前 `pytest.fail`，信息明确 |
| 访问未声明的 `users["userX_windows"]` | KeyError（现状） |
| mock 模式 | 同主平台 mock 资源合成伴生 |

## 8. 文档与测试

- AGENTS.md 五新增「伴生平台」小节；CLAUDE.md 速记一行
- `tests/unit/test_users_companion.py`：
  - 语法解析（正常 / 非法平台 / api 主平台 / 键冲突）
  - 伴生 User 属性与资源复用
  - 懒 hooks：使用触发、未使用不触发、失败上报
  - 报告与截图过滤
  - keepalive 只含主平台机器 ID
- 现有架构契约测试（tests/architecture）回归通过

## 9. 涉及文件

| 文件 | 改动 |
|------|------|
| `conftest.py` | users fixture：解析伴生、创建伴生 User、setup 懒执行、keepalive 过滤、报告/截图过滤 |
| `common/user.py` | setup 待执行槽 + `__getattr__` 触发点 |
| `common/users_marker.py`（新增） | `主+伴生` 语法解析纯函数 |
| `tests/unit/test_users_companion.py`（新增） | 单元测试 |
| `AGENTS.md` / `CLAUDE.md` | 文档 |
