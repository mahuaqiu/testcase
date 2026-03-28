# CLAUDE.md

## 项目概述

多端自动化测试框架，支持 Web/Windows/Mac/iOS/Android 五端。通过 HTTP 调用 testagent Worker 服务执行自动化操作。

## 架构：两层结构

```
testcases/                    # 测试用例目录
├── {平台}/                   # windows/web/mac/ios/android
│   └── {业务模块}/           # 如 login, meeting, share 等
│       └── test_*.py        # 测试用例文件
└── integration/              # 跨平台集成测试

aw/                          # 业务操作封装层
├── base_aw.py               # AW 基类
├── common/                  # 公共 AW
├── api/                     # API 平台 AW（HTTP 接口封装）
└── {平台}/                   # windows/web/mac/ios/android
    └── {业务模块}_aw.py      # 如 login_aw.py
```

**核心原则**：
- 一个测试文件 = 一条测试用例
- 测试用例通过 User 实例调用 AW 方法
- AW 类继承 BaseAW，使用便捷方法（`self.ocr_click(text)` 而非 `self.client.ocr_click(platform, text)`）

## 命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py` |
| AW 类 | `{业务名}AW` | `LoginAW` |
| AW 业务方法 | `do_{动作}` | `do_login()` |
| AW 断言方法 | `should_{期望}` | `should_login_success()` |
| 测试文件 | `test_{功能}_{场景}_{编号}.py` | `test_login_success_001.py` |
| 测试类 | `TestClass` | 固定名称 |
| 测试方法 | `test_{文件名}` | `test_login_success_001` |

## 用户资源与 User 代理

测试用例通过 `@pytest.mark.users()` 声明用户需求，User 实例自动加载 AW 并代理转发方法调用：

```python
@pytest.mark.users({"userA": "web"})
class TestClass:
    def test_login_success_001(self, users):
        userA = users["userA"]         # UI 用户
        userA_api = users["userA_api"] # API 用户（自动创建）

        # 直接通过 User 实例调用 AW 方法
        userA.do_login()
        userA.should_login_success()

        # API 用户调用 API AW 方法
        userA_api.do_create_meeting("test")
```

**User 属性**：`user_id`, `platform`, `ip`, `account`, `password`

## Hooks 配置

Hooks 用于测试用例执行前后自动执行操作（如启动/关闭应用）：

```yaml
# config.yaml
hooks:
  web:
    setup: ["start_app"]
    teardown: ["stop_app"]
  api:
    teardown: ["cancel_all_meetings"]
```

用例级别覆盖：
```python
@pytest.mark.hooks(setup=["+custom_hook"], teardown=["-stop_app"])
```

## API AW

API 平台用于数据准备和清理，无需 UI 操作：

```python
from aw.api.base_api_aw import BaseApiAW

class MeetingManageAW(BaseApiAW):
    def do_create_meeting(self, subject: str) -> MeetingInfo:
        """创建会议。"""
        result = self._post(CONFERENCE_URL, data={...})
        return self._parse_meeting_info(result)
```

声明 `@pytest.mark.users({"userA": "web"})` 时，自动创建 `userA`（UI）和 `userA_api`（API）两个 User 实例。

## 并行执行

多用户并行执行使用 `parallel()` 上下文：

```python
from common.parallel import parallel

with parallel():
    userA.do_login()
    userB.do_login()
    userC.do_login()
```

详细规范见 [AGENTS.md](AGENTS.md) 第六章。

## 详细规范

- 编码规范见 [AGENTS.md](AGENTS.md)
- AW 资源索引见 [aw/INDEX.md](aw/INDEX.md)