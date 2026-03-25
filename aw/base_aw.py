"""AW 基类。"""

import time
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from common.testagent_client import TestagentClient
from common.report_logger import ReportLogger

if TYPE_CHECKING:
    from common.user import User


class AWError(Exception):
    """AW 操作失败异常。"""

    def __init__(self, method: str, result: Dict[str, Any]):
        self.method = method
        self.result = result
        error_msg = result.get("error", "未知错误")
        super().__init__(f"{method} 执行失败: {error_msg}")


class BaseAW:
    """AW 基类。

    所有 AW 类继承此类，提供 client 和 user 的访问。
    自动记录日志并检查执行结果，失败时抛出 AWError。

    Args:
        client: TestagentClient 实例。
        user: User 实例（可选），用于获取账号密码等信息。
    """

    PLATFORM: str = ""  # 子类必须覆盖

    def __init__(self, client: TestagentClient, user: Optional["User"] = None):
        self.client = client
        self.user = user
        self._aw_name = self.__class__.__name__

    # ── 内部方法 ─────────────────────────────────────────

    def _execute_with_log(
        self,
        method: str,
        action: Callable[..., Dict[str, Any]],
        log_args: Dict[str, Any],
        *args: Any,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """执行操作并记录日志，失败时抛出异常。

        Args:
            method: 方法名。
            action: 实际执行的方法。
            log_args: 用于日志记录的参数（不含 platform）。
            *args, **kwargs: 传递给 action 的参数。

        Returns:
            执行结果。

        Raises:
            AWError: 执行失败时抛出。
        """
        logger = ReportLogger.get_current()
        start_time = time.time()

        try:
            result = action(*args, **kwargs)
        except Exception as e:
            # 记录异常
            duration_ms = int((time.time() - start_time) * 1000)
            logger.log_aw_call(
                aw_name=self._aw_name,
                method=method,
                args=log_args,
                success=False,
                result={"error": str(e)},
                duration_ms=duration_ms
            )
            raise

        duration_ms = int((time.time() - start_time) * 1000)
        success = result.get("status") == "success"

        # 记录 AW 调用日志
        user_id = self.user.user_id if self.user else ""
        logger.log_aw_call(
            aw_name=self._aw_name,
            method=method,
            args={"user_id": user_id, **log_args},
            success=success,
            result=result,
            duration_ms=duration_ms
        )

        # 记录 worker 调用日志（用于调试，报告中不显示）
        logger.log_worker_call(
            api="task/execute",
            params={"platform": self.PLATFORM, "method": method, "user_id": user_id, **log_args},
            success=success,
            response=result,
            duration_ms=duration_ms
        )

        # 失败时抛出异常
        if not success:
            raise AWError(f"{self._aw_name}.{method}", result)

        return result

    # ── 便捷方法 ─────────────────────────────────────────

    def ocr_click(self, text: str, **kwargs) -> dict:
        """OCR 识别并点击。"""
        return self._execute_with_log(
            "ocr_click",
            self.client.ocr_click,
            {"text": text, **kwargs},
            self.PLATFORM,
            text,
            **kwargs
        )

    def ocr_input(self, label: str, content: str, **kwargs) -> dict:
        """OCR 定位后输入。"""
        return self._execute_with_log(
            "ocr_input",
            self.client.ocr_input,
            {"label": label, "content": content, **kwargs},
            self.PLATFORM,
            label,
            content,
            **kwargs
        )

    def ocr_wait(self, text: str, **kwargs) -> dict:
        """等待文字出现。"""
        return self._execute_with_log(
            "ocr_wait",
            self.client.ocr_wait,
            {"text": text, **kwargs},
            self.PLATFORM,
            text,
            **kwargs
        )

    def click(self, x: int, y: int) -> dict:
        """坐标点击。"""
        return self._execute_with_log(
            "click",
            self.client.click,
            {"x": x, "y": y},
            self.PLATFORM,
            x,
            y
        )

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, **kwargs) -> dict:
        """滑动操作。"""
        return self._execute_with_log(
            "swipe",
            self.client.swipe,
            {"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y, **kwargs},
            self.PLATFORM,
            from_x,
            from_y,
            to_x,
            to_y,
            **kwargs
        )

    def start_app(self, app_id: str) -> dict:
        """启动应用。"""
        return self._execute_with_log(
            "start_app",
            self.client.start_app,
            {"app_id": app_id},
            self.PLATFORM,
            app_id
        )

    def stop_app(self, app_id: str) -> dict:
        """关闭应用。"""
        return self._execute_with_log(
            "stop_app",
            self.client.stop_app,
            {"app_id": app_id},
            self.PLATFORM,
            app_id
        )

    def navigate(self, url: str) -> dict:
        """导航到 URL（Web 端专用）。"""
        return self._execute_with_log(
            "navigate",
            self.client.navigate,
            {"url": url},
            self.PLATFORM,
            url
        )

    def screenshot(self) -> str:
        """截图并返回 base64。

        Returns:
            截图的 base64 编码，失败返回空字符串。
        """
        result = self.client.screenshot(self.PLATFORM)
        if result.get("status") == "success" and result.get("actions"):
            action = result["actions"][0]
            # 优先取 screenshot 字段，其次取 output 字段
            return action.get("screenshot") or action.get("output", "")
        return ""