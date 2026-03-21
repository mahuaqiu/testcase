"""
testagent HTTP 客户端封装。

提供与 testagent Worker 服务通信的统一接口，支持 Web/Win/Mac/iOS/Android 五端操作。

API 文档参考: api.yaml
"""

import time
from typing import Any, Dict, List, Optional

import requests


class TestagentClient:
    """testagent HTTP 客户端。

    通过 HTTP API 与 testagent Worker 服务通信，执行各端的自动化操作。

    Args:
        base_url: Worker 服务地址，默认 http://localhost:8080。
        timeout: 请求超时时间（秒），默认 300（5分钟）。

    Example:
        client = TestagentClient("http://localhost:8080")

        # 同步执行任务
        result = client.execute("web", [
            {"action_type": "navigate", "value": "https://example.com"},
            {"action_type": "ocr_click", "value": "登录"},
        ])

        # 异步执行任务
        task = client.execute_async("web", actions)
        result = client.get_task(task["task_id"])
    """

    def __init__(self, base_url: str = "http://localhost:8080", timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发送 HTTP 请求。

        Args:
            method: HTTP 方法（GET/POST/DELETE）。
            endpoint: API 端点路径。
            data: 请求体数据。
            params: URL 查询参数。

        Returns:
            响应 JSON 数据。

        Raises:
            TestagentError: 请求失败时抛出。
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            raise TestagentError(f"请求超时: {url}")
        except requests.exceptions.RequestException as e:
            raise TestagentError(f"请求失败: {e}") from e

    # ── Worker 状态与设备 ─────────────────────────────────────────────

    def get_worker_devices(self) -> Dict[str, Any]:
        """获取 Worker 状态和设备信息。

        Returns:
            Worker 状态及所有连接设备信息。
        """
        return self._request("GET", "/worker_devices")

    def refresh_devices(self) -> Dict[str, Any]:
        """刷新设备列表。

        Returns:
            刷新后的 Worker 状态及设备列表。
        """
        return self._request("POST", "/devices/refresh")

    # ── 任务执行（核心） ─────────────────────────────────────────────

    def execute(
        self,
        platform: str,
        actions: List[Dict[str, Any]],
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """同步执行任务。

        Args:
            platform: 平台类型（web/windows/mac/ios/android）。
            actions: 动作列表。
            device_id: 设备 ID（移动端必填）。
            user_id: 用户标识。
            config: 任务配置。

        Returns:
            任务执行结果。

        Example:
            result = client.execute("web", [
                {"action_type": "navigate", "value": "https://example.com"},
                {"action_type": "ocr_click", "value": "登录"},
                {"action_type": "ocr_input", "value": "用户名", "text": "admin", "offset": {"x": 100, "y": 0}},
            ])
        """
        task_request = {
            "platform": platform,
            "actions": actions,
        }

        if device_id:
            task_request["device_id"] = device_id
        if user_id:
            task_request["user_id"] = user_id
        if config:
            task_request["config"] = config

        return self._request("POST", "/task/execute", data=task_request)

    def execute_async(
        self,
        platform: str,
        actions: List[Dict[str, Any]],
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """异步执行任务。

        立即返回 task_id，任务在后台执行。

        Args:
            platform: 平台类型（web/windows/mac/ios/android）。
            actions: 动作列表。
            device_id: 设备 ID（移动端必填）。
            user_id: 用户标识。
            config: 任务配置。

        Returns:
            包含 task_id 和 status 的响应。

        Raises:
            TestagentError: 设备/平台冲突时抛出 409 错误。
        """
        task_request = {
            "platform": platform,
            "actions": actions,
        }

        if device_id:
            task_request["device_id"] = device_id
        if user_id:
            task_request["user_id"] = user_id
        if config:
            task_request["config"] = config

        return self._request("POST", "/task/execute_async", data=task_request)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """查询任务结果。

        一次性查询：查询后任务从内存中销毁，再次查询返回 404。

        Args:
            task_id: 任务 ID。

        Returns:
            任务状态或结果。

        Raises:
            TestagentError: 任务不存在时抛出 404 错误。
        """
        return self._request("GET", f"/task/{task_id}")

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """取消任务。

        如果只有一个 action，执行完再取消；
        有多个 action，当前 action 执行完后停止。

        Args:
            task_id: 任务 ID。

        Returns:
            取消结果。

        Raises:
            TestagentError: 任务不存在时抛出 404 错误。
        """
        return self._request("DELETE", f"/task/{task_id}")

    # ── 单步操作封装 ─────────────────────────────────────────────

    def ocr_click(
        self,
        platform: str,
        text: str,
        offset: Optional[Dict[str, int]] = None,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 文字识别点击。

        Args:
            platform: 平台类型。
            text: 要识别并点击的文字。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_click",
            "value": text,
            "timeout": timeout,
        }
        if offset:
            action["offset"] = offset

        return self.execute(platform, [action], device_id)

    def ocr_input(
        self,
        platform: str,
        label: str,
        text: str,
        offset: Optional[Dict[str, int]] = None,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 文字识别后输入。

        先定位文字位置，然后在偏移处输入内容。

        Args:
            platform: 平台类型。
            label: 要定位的文字标签。
            text: 要输入的内容。
            offset: 输入框相对文字的偏移量。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_input",
            "value": label,
            "text": text,
            "timeout": timeout,
        }
        if offset:
            action["offset"] = offset

        return self.execute(platform, [action], device_id)

    def ocr_wait(
        self,
        platform: str,
        text: str,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """等待 OCR 文字出现。

        Args:
            platform: 平台类型。
            text: 等待出现的文字。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_wait",
            "value": text,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id)

    def ocr_assert(
        self,
        platform: str,
        text: str,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 断言文字存在。

        Args:
            platform: 平台类型。
            text: 期望存在的文字。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_assert",
            "value": text,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id)

    def ocr_get_text(
        self,
        platform: str,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> str:
        """OCR 获取屏幕所有文字。

        Args:
            platform: 平台类型。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            识别到的文字内容。
        """
        action = {
            "action_type": "ocr_get_text",
            "value": "",
            "timeout": timeout,
        }
        result = self.execute(platform, [action], device_id)
        # 从结果中提取文字
        if result.get("status") == "success" and result.get("actions"):
            return result["actions"][0].get("output", "")
        return ""

    def image_click(
        self,
        platform: str,
        image_path: str,
        threshold: float = 0.8,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """图像识别点击。

        Args:
            platform: 平台类型。
            image_path: 图像模板路径。
            threshold: 匹配阈值（0-1）。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_click",
            "value": image_path,
            "threshold": threshold,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id)

    def image_wait(
        self,
        platform: str,
        image_path: str,
        threshold: float = 0.8,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """等待图像出现。

        Args:
            platform: 平台类型。
            image_path: 图像模板路径。
            threshold: 匹配阈值。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_wait",
            "value": image_path,
            "threshold": threshold,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id)

    def image_assert(
        self,
        platform: str,
        image_path: str,
        threshold: float = 0.8,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """图像断言。

        Args:
            platform: 平台类型。
            image_path: 图像模板路径。
            threshold: 匹配阈值。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_assert",
            "value": image_path,
            "threshold": threshold,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id)

    def click(
        self,
        platform: str,
        x: int,
        y: int,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """坐标点击。

        Args:
            platform: 平台类型。
            x: X 坐标。
            y: Y 坐标。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "click",
            "x": x,
            "y": y,
        }
        return self.execute(platform, [action], device_id)

    def swipe(
        self,
        platform: str,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        duration: int = 500,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """滑动操作。

        Args:
            platform: 平台类型。
            from_x: 起点 X 坐标。
            from_y: 起点 Y 坐标。
            to_x: 终点 X 坐标。
            to_y: 终点 Y 坐标。
            duration: 滑动持续时间（毫秒），默认 500ms。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "swipe",
            "from": {"x": from_x, "y": from_y},
            "to": {"x": to_x, "y": to_y},
            "duration": duration,
        }
        return self.execute(platform, [action], device_id)

    def input_text(
        self,
        platform: str,
        x: int,
        y: int,
        text: str,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在指定坐标输入文字。

        Args:
            platform: 平台类型。
            x: X 坐标。
            y: Y 坐标。
            text: 要输入的文字。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "input",
            "x": x,
            "y": y,
            "text": text,
        }
        return self.execute(platform, [action], device_id)

    def press(
        self,
        platform: str,
        key: str,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按键操作。

        Args:
            platform: 平台类型。
            key: 按键名称（如 Enter, Escape, ArrowDown, Control+A 等）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "press",
            "key": key,
        }
        return self.execute(platform, [action], device_id)

    def screenshot(
        self,
        platform: str,
        name: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """截图。

        Args:
            platform: 平台类型。
            name: 截图名称（可选）。
            device_id: 设备 ID。

        Returns:
            执行结果，包含截图数据。
        """
        action = {
            "action_type": "screenshot",
            "value": name or f"screenshot_{int(time.time())}",
        }
        return self.execute(platform, [action], device_id)

    def wait(
        self,
        platform: str,
        duration_ms: int,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """固定等待。

        Args:
            platform: 平台类型。
            duration_ms: 等待时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "wait",
            "value": str(duration_ms),
        }
        return self.execute(platform, [action], device_id)

    # ── Web 端专用 ─────────────────────────────────────────────

    def navigate(
        self,
        platform: str,
        url: str,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """导航到 URL（Web 端）。

        Args:
            platform: 平台类型。
            url: 目标 URL。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "navigate",
            "value": url,
        }
        return self.execute(platform, [action], device_id)

    # ── 应用操作 ─────────────────────────────────────────────

    def start_app(
        self,
        platform: str,
        value: str,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """启动应用/浏览器。

        Args:
            platform: 平台类型。
            value: 应用标识。
                - Web: 浏览器类型（chromium/firefox/webkit）
                - Android: 应用包名，如 "com.example.app"
                - iOS: Bundle ID，如 "com.example.app"
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "start_app",
            "value": value,
        }
        return self.execute(platform, [action], device_id)

    def stop_app(
        self,
        platform: str,
        value: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """关闭应用/浏览器。

        Args:
            platform: 平台类型。
            value: 应用标识（可选，不填则关闭当前应用）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "stop_app",
        }
        if value:
            action["value"] = value

        return self.execute(platform, [action], device_id)

    # ── 任务状态检查 ─────────────────────────────────────────────

    def is_success(self, result: Dict[str, Any]) -> bool:
        """检查任务是否执行成功。

        Args:
            result: execute() 返回的结果。

        Returns:
            是否成功。
        """
        return result.get("status") == "success"

    def get_error(self, result: Dict[str, Any]) -> Optional[str]:
        """获取任务错误信息。

        Args:
            result: execute() 返回的结果。

        Returns:
            错误信息，无错误返回 None。
        """
        if result.get("status") == "success":
            return None
        return result.get("error", "未知错误")

    def get_action_results(
        self,
        result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """获取各动作的执行结果。

        Args:
            result: execute() 返回的结果。

        Returns:
            动作结果列表。
        """
        return result.get("actions", [])


class TestagentError(Exception):
    """testagent 错误。"""

    pass