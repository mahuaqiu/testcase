"""
登录业务操作封装。

封装华为云会议登录相关流程，包括导航到登录页、执行登录、同意隐私政策等操作。
"""
from typing import Optional

from aw.base_aw import BaseAW
from variable import LoginVar

class LoginAW(BaseAW):
    """登录业务操作封装。

    封装华为云会议 Web 端登录流程，通过 OCR 识别和操作完成登录。

    Args:
        client: TestagentClient 实例。
        user: 用户资源实例（可选），用于动态获取账号密码。
    """

    PLATFORM = "web"

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_navigate_to_login(self, url: str) -> None:
        """导航到登录页面。

        步骤: 使用浏览器导航到指定的登录 URL。

        Args:
            url: 登录页面 URL。
        """
        self.navigate(url)
        self.wait(1)

    def do_login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """执行登录操作。

        步骤: 输入账号 → 输入密码 → 点击登录按钮。

        优先使用传入参数，其次使用 user 资源。

        Args:
            username: 用户名/手机号（可选）。
            password: 密码（可选）。

        Raises:
            ValueError: 未提供账号密码且无用户资源时抛出。
        """
        self.do_navigate_to_login(LoginVar.WEB_LOGIN_URL)
        # 优先使用传入参数，其次使用 user 资源
        account = username or (self.user.account if self.user else None)
        pwd = password or (self.user.password if self.user else None)

        if not account or not pwd:
            raise ValueError("未提供账号密码，且无用户资源")
        self.ocr_wait("邮箱/帐号",timeout=5000)
        self.wait(1)
        # 使用 OCR 识别并输入账号
        self.ocr_input("邮箱/帐号", account)
        # 使用 OCR 识别并输入密码
        self.ocr_input("密码", pwd)
        # 点击登录按钮
        self.ocr_click("登录")
        self.wait(1)
        self.do_accept_privacy()
        self.wait(1)

    def do_accept_privacy(self) -> None:
        """接受隐私政策。

        步骤: 点击同意/接受按钮。
        """
        self.ocr_click("同意")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_login_success(self) -> None:
        """断言登录成功。

        验证登录成功后页面显示"会议"文字。
        失败时会自动抛出 AWError。
        """
        self.ocr_wait("我的会议", timeout=5000)

    def should_show_error(self, error_msg: str) -> None:
        """断言显示错误提示。

        Args:
            error_msg: 期望的错误信息。

        失败时会自动抛出 AWError。
        """
        self.ocr_wait(error_msg, timeout=5000)