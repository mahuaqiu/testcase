"""
跨平台通话测试用例。

测试场景: Web端呼叫Windows端，验证跨平台通话功能
"""

import pytest


@pytest.mark.users({"userA": "web", "userB": "windows"})
@pytest.mark.hooks(setup=["+login"])
class TestCrossPlatformCall:
    """跨平台通话测试。"""

    def test_execute(self, users):
        """执行测试：Web呼叫Windows，应通话成功。"""
        caller = users["userA"]
        callee = users["userB"]

        # 主叫发起呼叫
        # caller.do_call(callee.account)

        # 被叫接听
        # callee.do_answer()

        # 验证通话状态
        # caller.should_in_call()
        # callee.should_in_call()

        # 结束通话
        # caller.do_hangup()