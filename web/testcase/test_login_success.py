"""
正确账号密码登录成功测试用例。

测试场景: 使用动态申请的用户资源登录华为云会议 Web 端
"""

import pytest

from common.testagent_client import TestagentClient
from web.aw.login_aw import LoginAW


@pytest.mark.users({"userA": "web"})
class TestLoginSuccess:
    """正确账号密码登录成功测试。"""

    def test_execute(self, users):
        """执行测试：正确账号密码登录，应登录成功。"""
        # 获取申请的用户资源
        user = users["userA"]

        # 创建客户端和 AW 实例
        client = TestagentClient()
        login_aw = LoginAW(client, user=user)

        # 执行测试
        login_aw.do_navigate_to_login("https://meeting.huaweicloud.com/#/login")
        login_aw.do_login()  # 使用 user 资源，无需传参
        login_aw.do_accept_privacy()
        login_aw.should_login_success()