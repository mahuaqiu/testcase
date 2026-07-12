"""
testagent HTTP 客户端封装。

提供与 testagent Worker 服务通信的统一接口，支持 Web/Win/Mac/iOS/Android 五端操作。

API 文档参考: api.yaml
"""

import time
import uuid
from typing import Any, Dict, List, Optional

import requests

_CONNECTION_ERROR_MARKERS = (
    "Connection aborted",
    "RemoteDisconnected",
    "Remote end closed connection",
    "ConnectionReset",
    "Connection reset",
    "Connection refused",
    "无法连接",
)
_TRANSPORT_ERROR_CODES = {
    "CONNECTION_TIMEOUT",
    "READ_TIMEOUT",
    "REQUEST_TIMEOUT",
    "CONNECTION_ERROR",
}


def _is_connection_closed_error(error: BaseException) -> bool:
    """判断异常是否属于允许自动重试的连接中断。"""
    if isinstance(error, requests.exceptions.ConnectionError):
        return True
    message = str(error)
    return any(marker in message for marker in _CONNECTION_ERROR_MARKERS)


def is_retryable_transport_error(error: BaseException) -> bool:
    """判断异常是否为传输层错误。"""
    code = getattr(error, "code", None)
    if code is not None:
        return bool(getattr(error, "retryable", False)) and code in _TRANSPORT_ERROR_CODES
    return _is_connection_closed_error(error) or any(
        marker in str(error) for marker in ("连接超时", "读取超时", "请求超时")
    )


class TestagentClient:
    """testagent HTTP 客户端。

    通过 HTTP API 与 testagent Worker 服务通信，执行各端的自动化操作。

    Args:
        base_url: Worker 服务地址，默认 http://localhost:8080。
        connect_timeout: TCP 连接超时（秒），默认 30。
        read_timeout: 读取响应超时（秒），默认 125。

    Example:
        client = TestagentClient("http://localhost:8080")

        # 同步执行任务
        result = client.execute("web", [
            {"action_type": "navigate", "value": "https://example.com"},
            {"action_type": "ocr_click", "value": "登录"},
        ])
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        connect_timeout: int = 30,
        read_timeout: int = 125,
    ):
        self.base_url = base_url.rstrip("/")
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    @staticmethod
    def _request_id(response: requests.Response) -> Optional[str]:
        """从响应头提取请求 ID。"""
        return response.headers.get("x-request-id") or response.headers.get("request-id")

    @staticmethod
    def _error_from_response(response: requests.Response) -> "TestagentError":
        """将 Worker 的结构化错误响应转换为统一异常。"""
        try:
            payload = response.json()
        except ValueError:
            payload = None

        detail = payload.get("detail") if isinstance(payload, dict) else None
        source = detail if isinstance(detail, dict) else {}
        message = source.get("message")
        if not message and isinstance(detail, str):
            message = detail
        if not message and isinstance(payload, dict):
            message = payload.get("message") or payload.get("error")
        if not message:
            message = (getattr(response, "text", "") or "").strip()
        if not message:
            message = getattr(response, "reason", "") or f"HTTP {response.status_code}"

        return TestagentError(
            str(message),
            code=source.get("code"),
            retryable=bool(source.get("retryable", False)),
            details=source.get("details"),
            status_code=response.status_code,
            request_id=TestagentClient._request_id(response),
        )

    @staticmethod
    def _decode_success(response: requests.Response) -> Dict[str, Any]:
        """解析成功响应，拒绝无效 JSON。"""
        try:
            payload = response.json()
        except ValueError as error:
            raise TestagentError(
                "Worker 返回无效 JSON",
                code="INVALID_RESPONSE",
                status_code=response.status_code,
                request_id=TestagentClient._request_id(response),
            ) from error
        if not isinstance(payload, dict):
            raise TestagentError(
                "Worker 返回无效响应",
                code="INVALID_RESPONSE",
                status_code=response.status_code,
                request_id=TestagentClient._request_id(response),
            )
        return payload

    def _new_session(self, headers: Optional[Dict[str, str]] = None) -> None:
        """重建 Session，并保留本次逻辑请求的自定义请求头。"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if headers:
            self.session.headers.update(headers)

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """发送 HTTP 请求，并在连接中断时复用请求头重试一次。"""
        url = f"{self.base_url}{endpoint}"
        timeout = (self.connect_timeout, self.read_timeout)

        def send() -> Dict[str, Any]:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=timeout,
                headers=headers,
            )
            if not 200 <= response.status_code < 300:
                raise self._error_from_response(response)
            return self._decode_success(response)

        try:
            return send()
        except requests.exceptions.ConnectTimeout as error:
            raise TestagentError(
                f"连接超时: {url}（{self.connect_timeout}秒）",
                code="CONNECTION_TIMEOUT",
                retryable=True,
            ) from error
        except requests.exceptions.ReadTimeout as error:
            raise TestagentError(
                f"读取超时: {url}（{self.read_timeout}秒）",
                code="READ_TIMEOUT",
                retryable=True,
            ) from error
        except requests.exceptions.Timeout as error:
            raise TestagentError(
                f"请求超时: {url}", code="REQUEST_TIMEOUT", retryable=True
            ) from error
        except TestagentError:
            raise
        except requests.exceptions.RequestException as error:
            if not _is_connection_closed_error(error):
                raise TestagentError(
                    f"请求失败: {error}", code="CONNECTION_ERROR", retryable=True
                ) from error

            self._new_session(headers)
            try:
                return send()
            except requests.exceptions.ConnectTimeout as retry_error:
                raise TestagentError(
                    f"连接超时: {url}（{self.connect_timeout}秒）",
                    code="CONNECTION_TIMEOUT",
                    retryable=True,
                ) from retry_error
            except requests.exceptions.ReadTimeout as retry_error:
                raise TestagentError(
                    f"读取超时: {url}（{self.read_timeout}秒）",
                    code="READ_TIMEOUT",
                    retryable=True,
                ) from retry_error
            except requests.exceptions.Timeout as retry_error:
                raise TestagentError(
                    f"请求超时: {url}",
                    code="REQUEST_TIMEOUT",
                    retryable=True,
                ) from retry_error
            except requests.exceptions.RequestException as retry_error:
                raise TestagentError(
                    f"请求失败（重试后）: {retry_error}",
                    code="CONNECTION_ERROR",
                    retryable=True,
                ) from retry_error
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
        level: Optional[str] = None,
        window: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """同步执行任务。

        Args:
            platform: 平台类型（web/windows/mac/ios/android）。
            actions: 动作列表。
            device_id: 设备 ID（移动端必填）。
            user_id: 用户标识。
            config: 任务配置。
            level: 执行层级（仅 Web 平台，browser/system）。
            window: 窗口定位参数（仅 Windows 平台，如 {"class": "HwmMainWndClass"}）。

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
        if level:
            task_request["level"] = level
        if window:
            task_request["window"] = window

        return self._request("POST", "/task/execute", data=task_request)

    def execute_async(
        self,
        platform: str,
        actions: List[Dict[str, Any]],
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        window: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """异步执行任务，并为本次逻辑调用固定一个幂等键。"""
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
        if window:
            task_request["window"] = window

        idempotency_key = idempotency_key or str(uuid.uuid4())
        return self._request(
            "POST",
            "/task/execute_async",
            data=task_request,
            headers={"Idempotency-Key": idempotency_key},
        )

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """查询任务结果。

        可重复查询：任务结果在 Worker 保留期内可重复读取。

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
        index: int = 0,
        click_duration: Optional[int] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 文字识别点击。

        Args:
            platform: 平台类型。
            text: 要识别并点击的文字。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            timeout: 超时时间（毫秒）。
            index: 选择第几个匹配结果（从 0 开始）。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_click",
            "value": text,
            "timeout": timeout,
            "index": index,
        }
        if offset:
            action["offset"] = offset
        if click_duration is not None:
            action["click_duration"] = click_duration

        return self.execute(platform, [action], device_id)

    def ocr_input(
        self,
        platform: str,
        label: str,
        text: str,
        offset: Optional[Dict[str, int]] = None,
        timeout: int = 5000,
        index: int = 0,
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
            index: 选择第几个匹配结果（从 0 开始）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_input",
            "value": label,
            "text": text,
            "timeout": timeout,
            "index": index,
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
        negate: bool = False,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 断言文字存在或不存在（单次截图断言）。

        Args:
            platform: 平台类型。
            text: 期望存在或不存在文字。
            negate: 断言不存在，True 时断言文字不存在。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_assert",
            "value": text,
            "negate": negate,
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

    def ocr_paste(
        self,
        platform: str,
        text: str,
        content: str,
        offset: Optional[Dict[str, int]] = None,
        timeout: int = 5000,
        index: int = 0,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 定位后粘贴剪贴板内容。

        Args:
            platform: 平台类型。
            text: 要定位的文字标签。
            content: 要粘贴的内容。
            offset: 点击偏移量。
            timeout: 超时时间（毫秒）。
            index: 选择第几个匹配结果（从 0 开始）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_paste",
            "value": text,
            "text": content,
            "timeout": timeout,
            "index": index,
        }
        if offset:
            action["offset"] = offset

        return self.execute(platform, [action], device_id)

    def ocr_move(
        self,
        platform: str,
        text: str,
        offset: Optional[Dict[str, int]] = None,
        timeout: int = 5000,
        index: int = 0,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """OCR 定位后移动鼠标。

        仅桌面端支持（Windows/Mac）。

        Args:
            platform: 平台类型。
            text: 要定位的文字。
            offset: 偏移量 {"x": 0, "y": 0}。
            timeout: 超时时间（毫秒）。
            index: 选择第几个匹配结果（从 0 开始）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "ocr_move",
            "value": text,
            "timeout": timeout,
            "index": index,
        }
        if offset:
            action["offset"] = offset

        return self.execute(platform, [action], device_id)

    # ── 图像识别动作 ─────────────────────────────────────────────

    def image_click(
        self,
        platform: str,
        image_base64: str,
        threshold: float = 0.8,
        timeout: int = 5000,
        index: int = 0,
        click_duration: Optional[int] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """图像识别点击。

        Args:
            platform: 平台类型。
            image_base64: 图像的 base64 编码。
            threshold: 匹配阈值（0-1）。
            timeout: 超时时间（毫秒）。
            index: 选择第几个匹配结果（从 0 开始）。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_click",
            "image_base64": image_base64,
            "threshold": threshold,
            "timeout": timeout,
            "index": index,
        }
        if click_duration is not None:
            action["click_duration"] = click_duration
        return self.execute(platform, [action], device_id)

    def image_wait(
        self,
        platform: str,
        image_base64: str,
        threshold: float = 0.8,
        timeout: int = 5000,
        index: int = 0,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """等待图像出现。

        Args:
            platform: 平台类型。
            image_base64: 图像的 base64 编码。
            threshold: 匹配阈值。
            timeout: 超时时间（毫秒）。
            index: 选择第几个匹配结果（从 0 开始）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_wait",
            "image_base64": image_base64,
            "threshold": threshold,
            "timeout": timeout,
            "index": index,
        }
        return self.execute(platform, [action], device_id)

    def image_assert(
        self,
        platform: str,
        image_base64: str,
        threshold: float = 0.8,
        negate: bool = False,
        index: int = 0,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """图像断言存在或不存在（单次截图断言）。

        Args:
            platform: 平台类型。
            image_base64: 图像的 base64 编码。
            threshold: 匹配阈值。
            negate: 断言不存在，True 时断言图像不存在。
            index: 选择第几个匹配结果（从 0 开始）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_assert",
            "image_base64": image_base64,
            "threshold": threshold,
            "negate": negate,
            "index": index,
        }
        return self.execute(platform, [action], device_id)

    def image_click_near_text(
        self,
        platform: str,
        image_base64: str,
        text: str,
        max_distance: int = 500,
        threshold: float = 0.8,
        timeout: int = 5000,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """点击文本附近最近的图像。

        Args:
            platform: 平台类型。
            image_base64: 图像的 base64 编码。
            text: 要查找的目标文字。
            max_distance: 最大搜索距离（像素），默认 500。
            threshold: 匹配阈值。
            timeout: 超时时间（毫秒）。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_click_near_text",
            "image_base64": image_base64,
            "value": text,
            "end_x": max_distance,
            "threshold": threshold,
            "timeout": timeout,
        }
        return self.execute(platform, [action], device_id)

    def image_move(
        self,
        platform: str,
        image_base64: str,
        threshold: float = 0.8,
        timeout: int = 5000,
        index: int = 0,
        offset: Optional[Dict[str, int]] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """图像识别后移动鼠标。

        仅桌面端支持（Windows/Mac）。

        Args:
            platform: 平台类型。
            image_base64: 图像的 base64 编码。
            threshold: 匹配阈值（0-1）。
            timeout: 超时时间（毫秒）。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 偏移量。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "image_move",
            "image_base64": image_base64,
            "threshold": threshold,
            "timeout": timeout,
            "index": index,
        }
        if offset:
            action["offset"] = offset

        return self.execute(platform, [action], device_id)

    def click(
        self,
        platform: str,
        x: int,
        y: int,
        click_duration: Optional[int] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """坐标点击。

        Args:
            platform: 平台类型。
            x: X 坐标。
            y: Y 坐标。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "click",
            "x": x,
            "y": y,
        }
        if click_duration is not None:
            action["click_duration"] = click_duration
        return self.execute(platform, [action], device_id)

    def move(
        self,
        platform: str,
        x: int,
        y: int,
        offset: Optional[Dict[str, int]] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """移动鼠标到指定坐标。

        仅桌面端支持（Windows/Mac）。

        Args:
            platform: 平台类型。
            x: X 坐标。
            y: Y 坐标。
            offset: 偏移量。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "move",
            "x": x,
            "y": y,
        }
        if offset:
            action["offset"] = offset

        return self.execute(platform, [action], device_id)

    def swipe(
        self,
        platform: str,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        duration: Optional[int] = None,
        steps: Optional[int] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """滑动操作。

        Args:
            platform: 平台类型。
            from_x: 起点 X 坐标。
            from_y: 起点 Y 坐标。
            to_x: 终点 X 坐标。
            to_y: 终点 Y 坐标。
            duration: 滑动持续时间（毫秒），默认使用 steps 参数控制。
            steps: 滑动步数，控制轨迹平滑度。默认 5 实现平滑滑动。
            device_id: 设备 ID。

        Returns:
            执行结果。
        """
        action = {
            "action_type": "swipe",
            "from": {"x": from_x, "y": from_y},
            "to": {"x": to_x, "y": to_y},
        }
        if duration is not None:
            action["duration"] = duration
        if steps is not None:
            action["steps"] = steps
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
        level: Optional[str] = None,
    ) -> Dict[str, Any]:
        """截图。

        Args:
            platform: 平台类型。
            name: 截图名称（可选）。
            device_id: 设备 ID。
            level: 执行层级（仅 Web 平台，browser/system）。

        Returns:
            执行结果，包含截图数据。
        """
        action = {
            "action_type": "screenshot",
            "value": name or f"screenshot_{int(time.time())}",
        }
        return self.execute(platform, [action], device_id, level=level)

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
    """testagent 结构化错误，保留旧版字符串异常行为。"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        retryable: bool = False,
        details: Any = None,
        status_code: Optional[int] = None,
        request_id: Optional[str] = None,
    ):
        self._code = code
        self._retryable = retryable
        self._details = details
        self._status_code = status_code
        self._request_id = request_id
        super().__init__(message)

    @property
    def code(self) -> Optional[str]:
        """错误码。"""
        return self._code

    @property
    def retryable(self) -> bool:
        """Worker 建议的重试属性。"""
        return self._retryable

    @property
    def details(self) -> Any:
        """结构化错误详情。"""
        return self._details

    @property
    def status_code(self) -> Optional[int]:
        """HTTP 状态码。"""
        return self._status_code

    @property
    def request_id(self) -> Optional[str]:
        """请求追踪 ID。"""
        return self._request_id
