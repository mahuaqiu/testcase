"""
Web端登录成功测试用例。

测试场景: 正确账号密码登录华为云会议 Web 端
"""

import pytest

from variable import LoginVar


@pytest.mark.users({"userA": "web"})
class TestLoginSuccess:
    """Web端登录成功测试。"""

    def test_execute(self, users):
        """执行测试：正确账号密码登录，应登录成功。"""
        user = users["userA"]

        user.do_navigate_to_login(LoginVar.WEB_LOGIN_URL)
        user.do_login()
        user.should_login_success()