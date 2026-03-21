# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

多端自动化测试框架，支持 Web/Windows/Mac/iOS/Android 五端。通过 HTTP 调用 testagent Worker 服务执行自动化操作。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行所有测试
pytest

# 运行指定平台测试
pytest -m windows
pytest -m web
pytest -m android
pytest -m ios
pytest -m mac

# 运行单个测试文件
pytest web/testcase/test_login_success.py

# 运行冒烟测试
pytest -m smoke

# 并行执行
pytest -n 4
```

## 架构：两层结构

```
testcase/
├── common/              # 公共模块
│   ├── testagent_client.py   # testagent HTTP 客户端
│   ├── assertions.py         # 断言函数
│   └── utils.py              # 工具函数
├── {平台}/               # windows/web/mac/ios/android
│   ├── aw/              # 业务操作封装层
│   └── testcase/        # 测试用例
└── config.yaml          # 配置文件
```

**核心原则**：
- testcase 层只调用 AW 层，不直接调用 testagent_client
- AW 层封装业务流程，通过 HTTP 调用 testagent 服务
- 一个测试文件 = 一条测试用例

## 命名规范

| 类型 | 命名规则 | 示例 |
|------|----------|------|
| AW 文件 | `{业务名}_aw.py` | `login_aw.py` |
| AW 类 | `{业务名}AW` | `LoginAW` |
| AW 业务方法 | `do_{动作}` | `do_login()` |
| AW 断言方法 | `should_{期望}` | `should_login_success()` |
| 测试文件 | `test_{功能}_{场景}.py` | `test_login_success.py` |
| 测试类 | `Test{功能}{场景}` | `TestLoginSuccess` |
| 测试方法 | `test_execute` | 固定方法名 |

## 用户资源管理

测试用例通过 `@pytest.mark.users()` 声明用户需求：

```python
@pytest.mark.users({"userA": "web"})
class TestLoginSuccess:
    def test_execute(self, users):
        user = users["userA"]
        # user.account, user.password, user.ip
```

## testagent 操作方法

| 方法 | 说明 |
|------|------|
| `ocr_click(platform, text)` | OCR 识别点击（推荐） |
| `ocr_input(platform, label, text)` | OCR 定位后输入 |
| `ocr_wait(platform, text)` | 等待文字出现 |
| `image_click(platform, image_path)` | 图像识别点击 |
| `click(platform, x, y)` | 坐标点击 |
| `swipe(platform, from_x, from_y, to_x, to_y)` | 滑动（移动端） |
| `navigate(platform, url)` | 导航 URL（Web） |
| `start_app(platform, value)` | 启动应用/浏览器 |
| `stop_app(platform, value)` | 关闭应用/浏览器 |

## 详细规范

完整编码规范见 [AGENTS.md](AGENTS.md)