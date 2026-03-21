"""AW 基类。"""

from typing import Optional

from common.testagent_client import TestagentClient


class BaseAW:
    """AW 基类。

    所有 AW 类继承此类，提供 client 和 user 的访问。

    Args:
        client: TestagentClient 实例。
        user: User 实例（可选），用于获取账号密码等信息。
    """

    PLATFORM: str = ""  # 子类必须覆盖

    def __init__(self, client: TestagentClient, user: Optional["User"] = None):
        self.client = client
        self.user = user

    # ── 便捷方法 ─────────────────────────────────────────

    def ocr_click(self, text: str, **kwargs) -> dict:
        """OCR 识别并点击。"""
        return self.client.ocr_click(self.PLATFORM, text, **kwargs)

    def ocr_input(self, label: str, content: str, **kwargs) -> dict:
        """OCR 定位后输入。"""
        return self.client.ocr_input(self.PLATFORM, label, content, **kwargs)

    def ocr_wait(self, text: str, **kwargs) -> dict:
        """等待文字出现。"""
        return self.client.ocr_wait(self.PLATFORM, text, **kwargs)

    def click(self, x: int, y: int) -> dict:
        """坐标点击。"""
        return self.client.click(self.PLATFORM, x, y)

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, **kwargs) -> dict:
        """滑动操作。"""
        return self.client.swipe(self.PLATFORM, from_x, from_y, to_x, to_y, **kwargs)

    def start_app(self, app_id: str) -> dict:
        """启动应用。"""
        return self.client.start_app(self.PLATFORM, app_id)

    def stop_app(self, app_id: str) -> dict:
        """关闭应用。"""
        return self.client.stop_app(self.PLATFORM, app_id)

    def navigate(self, url: str) -> dict:
        """导航到 URL（Web 端专用）。"""
        return self.client.navigate(self.PLATFORM, url)

    def screenshot(self) -> str:
        """截图并返回 base64。"""
        return self.client.screenshot(self.PLATFORM)