"""Web 应用操作封装。"""

from aw.base_aw import BaseAW


class InitAW(BaseAW):
    """Web 应用初始化操作封装。

    封装浏览器启动和关闭操作。

    Args:
        client: TestagentClient 实例。
        user: 用户资源实例（可选）。
    """

    PLATFORM = "web"

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_start_app(self, browser: str = "chrome") -> None:
        """启动浏览器。

        Args:
            browser: 浏览器名称，默认 chrome。支持 chrome、edge、safari 等。
        """
        self.start_app(browser)
        self.wait(1)

    def do_stop_app(self, browser: str = "chrome") -> None:
        """关闭浏览器。

        Args:
            browser: 浏览器名称，默认 chrome。支持 chrome、edge、safari 等。
        """
        self.stop_app(browser)