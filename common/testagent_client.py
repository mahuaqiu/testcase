"""
testagent HTTP 客户端封装。

提供与 testagent Worker 服务通信的统一接口，支持 Web/Win/Mac/iOS/Android 五端操作。

API 文档参考: api.yaml
"""

import time
import uuid
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

        # 执行单步操作
        result = client.execute("web", [
            {"action_type": "navigate", "value": "https://example.com"},
            {"action_type": "ocr_click", "value": "登录"},
        ])

        # 使用会话复用
        session = client.create_session("web")
        client.execute("web", actions, session_id=session["session_id"])
        client.close_session("web", session["session_id"])
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

    # ── 健康检查与状态 ─────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """健康检查。

        Returns:
            服务状态信息。
        """
        return self._request("GET", "/health")

    def get_status(self) -> Dict[str, Any]:
        """获取 Worker 状态。

        Returns:
            Worker 详细状态信息。
        """
        return self._request("GET", "/status")

    def get_info(self) -> Dict[str, Any]:
        """获取 Worker 详细信息。

        Returns:
            Worker 完整信息，包括支持的平台、设备列表等。
        """
        return self._request("GET", "/info")

    # ── 任务执行（核心） ─────────────────────────────────────────────

    def execute(
        self,
        platform: str,
        actions: List[Dict[str, Any]],
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行任务（同步）。

        Args:
            platform: 平台类型（web/windows/mac/ios/android）。
            actions: 动作列表。
            device_id: 设备 ID（移动端必填）。
            session_id: 会话 ID（复用会话时使用）。
            user_id: 用户标识。
            config: 任务配置。

        Returns:
            任务执行结果。

        Example:
            result = client.execute("web", [
                {"action_type": "navigate", "value": "https://example.com"},
                {"action_type": "ocr_click", "value": "登录"},
                {"action_type": "ocr_input", "value": "用户名", "offset": {"x": 100, "y": 0}},
            ])
        """
        task_request = {
            "platform": platform,
            "actions": actions,
        }

        if device_id:
            task_request["device_id"] = device_id
        if session_id:
            task_request["session_id"] = session_id
        if user_id:
            task_request["user_id"] = user_id
        if config:
            task_request["config"] = config

        return self._request("POST", "/task/execute", data=task_request)

    # ── 单步操作封装 ─────────────────────────────────────────────

    def ocr_click(
        self,
        platform: str,
        text: str,
        offset: Optional[Dict[str, int]] = None,
        timeout: int = 30000,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 文字识别点击。

        Args:
            platform: 平台类型。
            text: 要识别并点击的文字。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。
            session_id: 会话 ID。

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

        return self.execute(platform, [action], device_id, session_id)

    def ocr_input(
        self,
        platform: str,
        input_text: str,
        offset: Optional[Dict[str, int]] = None,
        timeout: int = 30000,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 文字识别后输入。

        先定位输入区域，然后输入内容。

        Args:
            platform: 平台类型。
            input_text: 要输入的内容。
            offset: 输入框相对文字的偏移量。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_input",
            "value": input_text,
            "timeout": timeout,
        }
        if offset:
            action["offset"] = offset

        return self.execute(platform, [action], device_id, session_id)

    def ocr_wait(
        self,
        platform: str,
        text: str,
        timeout: int = 30000,
        match_mode: str = "exact",
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """等待 OCR 文字出现。

        Args:
            platform: 平台类型。
            text: 等待出现的文字。
            timeout: 超时时间（毫秒）。
            match_mode: 匹配模式（exact/fuzzy/contains/regex）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_wait",
            "value": text,
            "timeout": timeout,
            "match_mode": match_mode,
        }
        return self.execute(platform, [action], device_id, session_id)

    def ocr_assert(
        self,
        platform: str,
        text: str,
        match_mode: str = "exact",
        timeout: int = 30000,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 断言文字存在。

        Args:
            platform: 平台类型。
            text: 期望存在的文字。
            match_mode: 匹配模式。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_assert",
            "value": text,
            "match_mode": match_mode,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id, session_id)

    def ocr_get_text(
        self,
        platform: str,
        text: str,
        match_mode: str = "exact",
        timeout: int = 30000,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """OCR 获取文字。

        Args:
            platform: 平台类型。
            text: 要定位的文字。
            match_mode: 匹配模式。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            识别到的文字内容。
        """
        action = {
            "action_type": "ocr_get_text",
            "value": text,
            "match_mode": match_mode,
            "timeout": timeout,
        }
        result = self.execute(platform, [action], device_id, session_id)
        # 从结果中提取文字
        if result.get("status") == "success" and result.get("actions"):
            return result["actions"][0].get("output", "")
        return ""

    def image_click(
        self,
        platform: str,
        image_path: str,
        threshold: float = 0.8,
        timeout: int = 30000,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """图像识别点击。

        Args:
            platform: 平台类型。
            image_path: 图像模板路径。
            threshold: 匹配阈值（0-1）。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_click",
            "image_path": image_path,
            "threshold": threshold,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id, session_id)

    def image_wait(
        self,
        platform: str,
        image_path: str,
        threshold: float = 0.8,
        timeout: int = 30000,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """等待图像出现。

        Args:
            platform: 平台类型。
            image_path: 图像模板路径。
            threshold: 匹配阈值。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_wait",
            "image_path": image_path,
            "threshold": threshold,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id, session_id)

    def image_assert(
        self,
        platform: str,
        image_path: str,
        threshold: float = 0.8,
        timeout: int = 30000,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """图像断言。

        Args:
            platform: 平台类型。
            image_path: 图像模板路径。
            threshold: 匹配阈值。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_assert",
            "image_path": image_path,
            "threshold": threshold,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id, session_id)

    def click(
        self,
        platform: str,
        x: int,
        y: int,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """坐标点击。

        Args:
            platform: 平台类型。
            x: X 坐标。
            y: Y 坐标。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "click",
            "x": x,
            "y": y,
        }
        return self.execute(platform, [action], device_id, session_id)

    def swipe(
        self,
        platform: str,
        direction: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        end_x: Optional[int] = None,
        end_y: Optional[int] = None,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """滑动操作。

        Args:
            platform: 平台类型。
            direction: 滑动方向（up/down/left/right）。
            x: 起点 X 坐标（可选）。
            y: 起点 Y 坐标（可选）。
            end_x: 终点 X 坐标（可选）。
            end_y: 终点 Y 坐标（可选）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "swipe",
            "direction": direction,
        }
        if x is not None:
            action["x"] = x
        if y is not None:
            action["y"] = y
        if end_x is not None:
            action["end_x"] = end_x
        if end_y is not None:
            action["end_y"] = end_y

        return self.execute(platform, [action], device_id, session_id)

    def input_text(
        self,
        platform: str,
        text: str,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """输入文字。

        Args:
            platform: 平台类型。
            text: 要输入的文字。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "input",
            "value": text,
        }
        return self.execute(platform, [action], device_id, session_id)

    def press(
        self,
        platform: str,
        key: str,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按键操作。

        Args:
            platform: 平台类型。
            key: 按键值（如 Enter, Escape, Backspace 等）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "press",
            "value": key,
        }
        return self.execute(platform, [action], device_id, session_id)

    def screenshot(
        self,
        platform: str,
        name: Optional[str] = None,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """截图。

        Args:
            platform: 平台类型。
            name: 截图名称（可选）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果，包含截图数据。
        """
        action = {
            "action_type": "screenshot",
            "value": name or f"screenshot_{int(time.time())}",
        }
        return self.execute(platform, [action], device_id, session_id)

    def wait(
        self,
        platform: str,
        duration_ms: int,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """等待。

        Args:
            platform: 平台类型。
            duration_ms: 等待时间（毫秒）。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "wait",
            "wait": duration_ms,
        }
        return self.execute(platform, [action], device_id, session_id)

    # ── Web 端专用 ─────────────────────────────────────────────

    def navigate(
        self,
        platform: str,
        url: str,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """导航到 URL（Web 端）。

        Args:
            platform: 平台类型。
            url: 目标 URL。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "navigate",
            "value": url,
        }
        return self.execute(platform, [action], device_id, session_id)

    # ── 应用操作（App 端） ─────────────────────────────────────────────

    def launch_app(
        self,
        platform: str,
        app_path: Optional[str] = None,
        bundle_id: Optional[str] = None,
        package_name: Optional[str] = None,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """启动应用。

        Args:
            platform: 平台类型。
            app_path: 应用路径（Windows/Mac）。
            bundle_id: iOS Bundle ID。
            package_name: Android 包名。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "launch_app",
        }
        if app_path:
            action["app_path"] = app_path
        if bundle_id:
            action["bundle_id"] = bundle_id
        if package_name:
            action["package_name"] = package_name

        return self.execute(platform, [action], device_id, session_id)

    def close_app(
        self,
        platform: str,
        bundle_id: Optional[str] = None,
        package_name: Optional[str] = None,
        device_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """关闭应用。

        Args:
            platform: 平台类型。
            bundle_id: iOS Bundle ID。
            package_name: Android 包名。
            device_id: 设备 ID。
            session_id: 会话 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "close_app",
        }
        if bundle_id:
            action["bundle_id"] = bundle_id
        if package_name:
            action["package_name"] = package_name

        return self.execute(platform, [action], device_id, session_id)

    # ── 会话管理 ─────────────────────────────────────────────

    def create_session(
        self,
        platform: str,
        device_id: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建会话。

        创建一个新的自动化会话，可用于复用浏览器/应用实例。

        Args:
            platform: 平台类型。
            device_id: 设备 ID（移动端）。
            options: 会话选项（如 headless, browser_type 等）。

        Returns:
            会话信息，包含 session_id。
        """
        data = {"platform": platform}
        if device_id:
            data["device_id"] = device_id
        if options:
            data["options"] = options

        return self._request("POST", "/session", data=data)

    def get_session(
        self,
        platform: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """获取会话状态。

        Args:
            platform: 平台类型。
            session_id: 会话 ID。

        Returns:
            会话状态信息。
        """
        return self._request(
            "GET",
            f"/session/{session_id}",
            params={"platform": platform},
        )

    def close_session(
        self,
        platform: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """关闭会话。

        Args:
            platform: 平台类型。
            session_id: 会话 ID。

        Returns:
            关闭结果。
        """
        return self._request(
            "DELETE",
            f"/session/{session_id}",
            params={"platform": platform},
        )

    # ── 设备管理 ─────────────────────────────────────────────

    def get_devices(self) -> List[Dict[str, Any]]:
        """获取设备列表。

        Returns:
            设备列表。
        """
        return self._request("GET", "/devices")

    def refresh_devices(self) -> Dict[str, Any]:
        """刷新设备列表。

        Returns:
            刷新结果，包含新增和移除的设备。
        """
        return self._request("POST", "/devices/refresh")

    def get_screenshot(
        self,
        platform: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """获取实时截图。

        Args:
            platform: 平台类型。
            session_id: 会话 ID。

        Returns:
            截图数据（base64）。
        """
        return self._request(
            "POST",
            "/screenshot",
            data={"platform": platform, "session_id": session_id},
        )

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