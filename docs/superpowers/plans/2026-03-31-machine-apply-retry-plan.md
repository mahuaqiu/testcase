# 机器申请重试机制实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 UserManager._apply_remote 方法添加重试机制，当机器资源不足时等待后重试。

**Architecture:** 修改 user_manager.py，提取 _parse_response 方法，在 _apply_remote 中实现重试循环。配置通过 config.yaml 传入。

**Tech Stack:** Python, pytest, requests

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `common/user_manager.py` | 修改 | 添加重试逻辑，提取 _parse_response 方法 |
| `config.yaml` | 修改 | 添加 retry 配置项 |
| `tests/common/test_user_manager.py` | 创建 | 单元测试 |

---

### Task 1: 添加 retry 配置项

**Files:**
- Modify: `config.yaml:9-10`

- [ ] **Step 1: 在 config.yaml 的 resource_manager 下添加 retry 配置**

在 `timeout: 30` 后添加：

```yaml
  # 重试配置
  retry:
    max_wait_seconds: 900   # 最多等待15分钟
    retry_interval: 15      # 重试间隔15秒
    retryable_errors:       # 可重试的错误类型
      - "env not enough"
```

- [ ] **Step 2: 确认配置格式正确**

运行: `python -c "from common.config_loader import ConfigLoader; c = ConfigLoader().load(); print(c.get('resource_manager', {}).get('retry', {}))"`

预期输出: `{'max_wait_seconds': 900, 'retry_interval': 15, 'retryable_errors': ['env not enough']}`

- [ ] **Step 3: 提交**

```bash
git add config.yaml
git commit -m "feat(config): 添加机器申请重试配置项"
```

---

### Task 2: 创建单元测试文件

**Files:**
- Create: `tests/common/test_user_manager.py`

- [ ] **Step 1: 创建测试目录和文件**

```bash
mkdir -p tests/common
touch tests/__init__.py tests/common/__init__.py
```

- [ ] **Step 2: 编写测试 - 正常申请成功无重试**

```python
"""UserManager 单元测试。"""

import pytest
from unittest.mock import Mock, patch
from common.user_manager import UserManager, UserManagerError


class TestApplyRemoteRetry:
    """测试 _apply_remote 重试机制。"""

    def test_apply_success_no_retry(self):
        """正常申请成功，不触发重试。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30,
                "retry": {
                    "max_wait_seconds": 900,
                    "retry_interval": 15,
                    "retryable_errors": ["env not enough"]
                }
            }
        })

        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "userA": {
                    "ip": "192.168.0.1",
                    "port": 8080,
                    "account": "test",
                    "password": "pass",
                    "device_type": "web",
                    "id": "machine-1"
                }
            }
        }
        mock_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', return_value=mock_response):
            result = manager._apply_remote({"userA": "web"})
            assert "userA" in result
            assert result["userA"].ip == "192.168.0.1"
```

- [ ] **Step 3: 运行测试确认失败**

运行: `source .venv/bin/activate && pytest tests/common/test_user_manager.py -v`

预期: PASS（因为现有代码支持此场景）

- [ ] **Step 4: 编写测试 - env not enough 触发重试最终成功**

```python
    def test_apply_env_not_enough_retry_success(self):
        """机器不足触发重试，最终成功。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30,
                "retry": {
                    "max_wait_seconds": 45,  # 测试用短时间
                    "retry_interval": 15,
                    "retryable_errors": ["env not enough"]
                }
            }
        })

        # 第一次返回 env not enough，第二次返回成功
        fail_response = Mock()
        fail_response.json.return_value = {"status": "fail", "result": "env not enough"}
        fail_response.raise_for_status = Mock()

        success_response = Mock()
        success_response.json.return_value = {
            "status": "success",
            "data": {
                "userA": {
                    "ip": "192.168.0.1",
                    "port": 8080,
                    "account": "test",
                    "password": "pass",
                    "device_type": "web",
                    "id": "machine-1"
                }
            }
        }
        success_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', side_effect=[fail_response, success_response]):
            with patch('time.sleep') as mock_sleep:
                result = manager._apply_remote({"userA": "web"})
                assert "userA" in result
                mock_sleep.assert_called_once_with(15)
```

- [ ] **Step 5: 运行测试确认失败**

运行: `pytest tests/common/test_user_manager.py::TestApplyRemoteRetry::test_apply_env_not_enough_retry_success -v`

预期: FAIL - 因为现有代码不支持重试

- [ ] **Step 6: 编写测试 - env not enough 重试超时失败**

```python
    def test_apply_env_not_enough_retry_timeout(self):
        """机器不足重试超时，最终失败。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30,
                "retry": {
                    "max_wait_seconds": 45,
                    "retry_interval": 15,
                    "retryable_errors": ["env not enough"]
                }
            }
        })

        # 每次都返回 env not enough（最多重试 3 次）
        fail_response = Mock()
        fail_response.json.return_value = {"status": "fail", "result": "env not enough"}
        fail_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', return_value=fail_response):
            with patch('time.sleep') as mock_sleep:
                with pytest.raises(UserManagerError) as exc_info:
                    manager._apply_remote({"userA": "web"})
                assert "机器资源不足" in str(exc_info.value)
                assert mock_sleep.call_count == 3  # 45/15=3 次重试
```

- [ ] **Step 7: 编写测试 - 其他错误直接失败**

```python
    def test_apply_other_error_no_retry(self):
        """其他错误直接失败，不重试。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30,
                "retry": {
                    "max_wait_seconds": 900,
                    "retry_interval": 15,
                    "retryable_errors": ["env not enough"]
                }
            }
        })

        fail_response = Mock()
        fail_response.json.return_value = {"status": "fail", "result": "account locked"}
        fail_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', return_value=fail_response):
            with patch('time.sleep') as mock_sleep:
                with pytest.raises(UserManagerError) as exc_info:
                    manager._apply_remote({"userA": "web"})
                assert "account locked" in str(exc_info.value)
                mock_sleep.assert_not_called()
```

- [ ] **Step 8: 编写测试 - 配置缺失使用默认值**

```python
    def test_apply_default_config(self):
        """配置缺失时使用默认值。"""
        manager = UserManager({
            "resource_manager": {
                "base_url": "http://test",
                "namespace": "test",
                "timeout": 30
            }
        })

        fail_response = Mock()
        fail_response.json.return_value = {"status": "fail", "result": "env not enough"}
        fail_response.raise_for_status = Mock()

        with patch.object(manager._session, 'post', return_value=fail_response):
            with patch('time.sleep') as mock_sleep:
                with pytest.raises(UserManagerError):
                    manager._apply_remote({"userA": "web"})
                # 默认值: 900/15 = 60 次重试
                assert mock_sleep.call_count == 60
```

- [ ] **Step 9: 提交测试文件**

```bash
git add tests/__init__.py tests/common/__init__.py tests/common/test_user_manager.py
git commit -m "test(user_manager): 添加重试机制单元测试"
```

---

### Task 3: 实现重试逻辑

**Files:**
- Modify: `common/user_manager.py:1-10,154-202`

- [ ] **Step 1: 添加 import time**

在文件顶部 `import requests` 后添加：

```python
import time
```

- [ ] **Step 2: 提取 _parse_response 方法**

在 `_apply_remote` 方法后添加新方法：

```python
def _parse_response(self, data: dict, users: Dict[str, str]) -> Dict[str, UserResource]:
    """解析成功响应，提取用户资源。

    Args:
        data: API 成功响应数据。
        users: 用户需求字典。

    Returns:
        用户资源字典。
    """
    resources_data = data.get("data", {})
    # 保存原始响应中的机器 ID（用于 keepalive 和 release）
    self._raw_resources = {
        user_id: user_data for user_id, user_data in resources_data.items()
    }

    # 解析响应
    for user_id, user_data in resources_data.items():
        self._resources[user_id] = UserResource(
            user_id=user_id,
            platform=user_data.get("device_type", users.get(user_id, "")),
            ip=user_data.get("ip", ""),
            port=user_data.get("port", 8080),
            account=user_data.get("account", ""),
            password=user_data.get("password", ""),
            user_type=user_data.get("type", "normal"),
            machine_id=user_data.get("id"),
            extra=user_data.get("extra", {}),
        )

    return self._resources
```

- [ ] **Step 3: 重写 _apply_remote 方法实现重试**

替换 `_apply_remote` 方法（第154-202行）：

```python
def _apply_remote(self, users: Dict[str, str]) -> Dict[str, UserResource]:
    """远程模式：调用 API 申请资源，支持重试。

    Args:
        users: 用户需求字典。

    Returns:
        用户资源字典。

    Raises:
        UserManagerError: API 调用失败时抛出。
    """
    # 加载重试配置
    retry_config = self.config.get("resource_manager", {}).get("retry", {})
    max_wait_seconds = retry_config.get("max_wait_seconds", 900)
    retry_interval = retry_config.get("retry_interval", 15)
    retryable_errors = retry_config.get("retryable_errors", ["env not enough"])

    max_retries = max_wait_seconds // retry_interval

    url = f"{self._base_url}/env/{self._namespace}/application"

    for attempt in range(max_retries + 1):
        # 发起申请请求
        try:
            response = self._session.post(url, json=users, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as e:
            raise UserManagerError(f"申请用户资源超时: {e}") from e
        except requests.RequestException as e:
            raise UserManagerError(f"申请用户资源失败: {e}") from e

        # 检查响应状态
        if data.get("status") == "success":
            return self._parse_response(data, users)

        error_msg = data.get("result", "未知错误")

        # 判断是否可重试
        if error_msg in retryable_errors:
            if attempt < max_retries:
                import logging
                logging.info(
                    f"机器资源不足，等待 {retry_interval} 秒后重试（第 {attempt+1}/{max_retries} 次）"
                )
                time.sleep(retry_interval)
                continue
            else:
                raise UserManagerError(
                    f"申请用户资源失败：机器资源不足，已等待 {max_wait_seconds} 秒"
                )
        else:
            # 其他错误直接失败
            raise UserManagerError(f"申请用户资源失败: {error_msg}")
```

- [ ] **Step 4: 运行所有测试确认通过**

运行: `source .venv/bin/activate && pytest tests/common/test_user_manager.py -v`

预期: 所有测试 PASS

- [ ] **Step 5: 提交实现**

```bash
git add common/user_manager.py
git commit -m "feat(user_manager): 实现机器申请重试机制"
```

---

### Task 4: 验证集成测试

**Files:**
- Run existing testcases to verify integration

- [ ] **Step 1: 运行现有测试用例验证无破坏**

运行: `source .venv/bin/activate && pytest testcases/ -v --collect-only`

确认能正常收集测试用例。

- [ ] **Step 2: 最终提交（如有遗漏文件）**

```bash
git status
git add -A
git commit -m "feat: 机器申请重试机制完成"
```