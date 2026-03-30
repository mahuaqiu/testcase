# 机器申请重试机制设计

## 背景

当前 `UserManager._apply_remote()` 方法在申请失败时直接抛出异常，不支持重试。当机器资源不足（返回 `env not enough`）时，应该等待后重试，而不是立即失败。

## 目标

1. 机器资源不足时，sleep 15秒后重试，最多等待15分钟
2. 其他错误时，直接抛出异常，不可重试
3. 记录每次重试的日志

## 设计

### 修改文件

- `common/user_manager.py` - 修改 `_apply_remote()` 方法
- `config.yaml` - 新增 retry 配置项

### 配置结构

```yaml
resource_manager:
  base_url: "http://xxx"
  timeout: 30
  retry:
    max_wait_seconds: 900   # 最多等待15分钟
    retry_interval: 15      # 重试间隔15秒
    retryable_errors:       # 可重试的错误类型
      - "env not enough"
```

### 重试逻辑

```python
def _apply_remote(self, users: Dict[str, str]) -> Dict[str, UserResource]:
    """远程模式：调用 API 申请资源，支持重试。"""

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

        if data.get("status") == "success":
            return self._parse_response(data, users)

        error_msg = data.get("result", "未知错误")

        if error_msg in retryable_errors:
            if attempt < max_retries:
                logger.info(f"机器资源不足，等待 {retry_interval} 秒后重试（第 {attempt+1}/{max_retries} 次）")
                time.sleep(retry_interval)
                continue
            else:
                raise UserManagerError(f"申请用户资源失败：机器资源不足，已等待 {max_wait_seconds} 秒")
        else:
            raise UserManagerError(f"申请用户资源失败: {error_msg}")

def _parse_response(self, data: dict, users: Dict[str, str]) -> Dict[str, UserResource]:
    """解析成功响应，提取用户资源。"""
    resources_data = data.get("data", {})
    self._raw_resources = {
        user_id: user_data for user_id, user_data in resources_data.items()
    }

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

### 日志输出示例

```
机器资源不足，等待 15 秒后重试（第 1/60 次）
机器资源不足，等待 15 秒后重试（第 2/60 次）
...
申请用户资源失败：机器资源不足，已等待 900 秒
```

## 测试要点

1. 正常申请成功，无重试
2. 返回 `env not enough`，触发重试，最终成功
3. 返回 `env not enough`，触发重试，最终超时失败
4. 返回其他错误（如 `account locked`），直接失败，无重试
5. 配置缺失时，使用默认值（900秒/15秒）

## 向后兼容

- 配置项可选，缺失时使用默认值
- 不影响现有测试用例调用方式