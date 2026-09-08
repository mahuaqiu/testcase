# CLAUDE.md

多端自动化测试工程：testcases 层用 pytest 写用例，AW 层封装业务操作，通过 HTTP
调用 testagent Worker 在 Web/Windows/Mac/iOS/Android 等多端执行。

**完整规范见 [AGENTS.md](AGENTS.md)，本文档只是速查要点。**

## 核心规则速记

- **一个测试文件 = 一条测试用例**：`test_{功能}_{场景}_{编号}.py`，类固定 `TestClass`，
  方法 `test_{文件名}`
- **AW 方法前缀**：业务 `do_`、断言 `should_`，中文 docstring（首行自动作为报告步骤标题）
- **测试只调 User 实例**：`users["userA"].do_login()`，不直接调 testagent_client；
  `userA_api` 随 `userA` 自动创建（API 数据准备/清理）
- **用户声明**：`@pytest.mark.users({"userA": "web"})`，User 属性见 AGENTS.md 5.1
- **并行**：`with parallel():` 块内只放操作（多用户登录/入会等），验证放块外顺序执行
- **Hooks**：`@pytest.mark.hooks(setup=["+x", "-y", {"z": arg}])`；目录 conftest 用
  `get_hooks()` 提供公共层，多级全部叠加，用例层 > 内层 conftest > 外层 > config.yaml
- **配置读取**：用例/AW/目录 conftest 一律 `from common.runtime import get_config,
  get_exe_param`，不要 `from conftest import`（模块名冲突）

## 最小用例骨架

```python
"""Web端登录成功测试用例。"""

import pytest


@pytest.mark.users({"userA": "web"})
class TestClass:
    """Web端登录成功测试。"""

    def test_login_success_001(self, users):
        """执行测试：正确账号密码登录，应登录成功。"""
        userA = users["userA"]
        userA.do_login()
        userA.should_login_success()
```

## 详细规范索引

| 主题 | AGENTS.md 章节 |
|------|----------------|
| 项目架构与目录结构 | 一 |
| 命名规范 | 二 |
| AW 层编码规范（BaseAW 便捷方法） | 三 |
| testcase 层编码规范 | 四 |
| 用户资源管理（User 代理 / namespace / exeParam） | 五 |
| 并行执行模式（parallel） | 六 |
| Hooks 配置（分层覆盖 / app_type / 目录 conftest） | 七 |
| API AW 模块（BaseApiAW） | 八 |
| Skill 生成代码检查清单 | 九 |
| 完整示例 | 十 |

AW 资源索引见 [aw/INDEX.md](aw/INDEX.md)。
