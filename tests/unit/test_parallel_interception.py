"""AW 拦截点（收集模式）单元测试。"""

from unittest.mock import Mock

import pytest

from aw.api.base_api_aw import BaseApiAW
from aw.base_aw import BaseAW
from common.parallel import CallTask, PendingCall, parallel


def make_user(user_id="userA", platform="web"):
    user = Mock()
    user.user_id = user_id
    user.platform = platform
    user.account = "acc"
    user.password = "pwd"
    user.name = "Name"
    user.ip = "127.0.0.1"
    user.device_id = ""
    return user


class DemoAW(BaseAW):
    """含取值/分支逻辑的演示 AW。"""

    PLATFORM = "web"

    def do_login(self):
        """执行登录。"""
        if self.ocr_exist("已登录"):
            return "skip"
        self.ocr_click("登录")
        return "ok"

    def should_see_main(self):
        """断言主界面。"""
        text = self.ocr_get_text()
        assert "会议" in text


class FakeApiAW(BaseApiAW):
    """API AW 演示（继承装饰机制）。"""

    PLATFORM = "api"
    _LOGIN_URL = "https://example.com/login"
    fetched = []  # 方法体内记录真实执行（spy 包装饰后方法只能看到 PendingCall）

    def do_fetch(self):
        """拉取数据。"""
        self.fetched.append({"id": 1})
        return {"id": 1}


class NestedAW(BaseAW):
    """内部使用 parallel() 的 AW（嵌套场景）。"""

    PLATFORM = "web"

    def do_double_click(self):
        """并行执行两次点击。"""
        with parallel():
            self.ocr_click("按钮A")
            self.ocr_click("按钮B")


def exist_result(exists):
    output = f'{{"exists": {str(exists).lower()}}}'
    return {"actions": [{"status": "success", "output": output}]}


def click_result():
    return {"actions": [{"status": "success"}]}


def text_result(text):
    # worker 契约：ocr_get_text 的 output 即纯文本（client 层直接取 actions[0].output）
    return {"actions": [{"status": "success", "output": text}]}


def test_business_method_collected_not_executed():
    """收集模式下业务方法不执行，入队为一个 CallTask。"""
    client = Mock()
    client.execute.side_effect = [exist_result(True)]  # 退出块后 do_login 干净执行
    aw = DemoAW(client, make_user())

    with parallel() as context:
        result = aw.do_login()

        assert client.execute.call_count == 0  # 收集期不发起请求
        assert len(context._tasks) == 1
        assert context._tasks[0].user_id == "userA"
        assert context._tasks[0].method == "do_login"
        assert isinstance(result, PendingCall)


def test_business_method_executes_after_block():
    """退出块后业务方法在执行线程内真实运行，分支按执行期结果走。"""
    client = Mock()
    client.execute.side_effect = [exist_result(False), click_result()]
    aw = DemoAW(client, make_user())

    with parallel():
        aw.do_login()

    assert client.execute.call_count == 2  # exist=False → 走 ocr_click 分支


def test_branch_takes_other_path_when_exists():
    """分支按执行期真实结果选择（exists=True 时跳过点击）。"""
    client = Mock()
    client.execute.side_effect = [exist_result(True)]
    aw = DemoAW(client, make_user())

    with parallel():
        aw.do_login()

    assert client.execute.call_count == 1  # exist=True → 不点击


def test_should_method_with_get_text_runs_in_parallel():
    """含 ocr_get_text 取值断言的方法可并行执行。"""
    client = Mock()
    client.execute.side_effect = [text_result("我的会议")]
    aw = DemoAW(client, make_user())

    with parallel():
        aw.should_see_main()  # 不抛断言错误即通过

    assert client.execute.call_count == 1


def test_direct_atomic_call_collected():
    """块内直接调原子操作同样入队，退出后执行。"""
    client = Mock()
    client.execute.side_effect = [click_result()]
    aw = DemoAW(client, make_user())

    with parallel() as context:
        aw.ocr_click("登录")

    assert len(context._tasks) == 1
    assert context._tasks[0].method == "ocr_click"
    assert client.execute.call_count == 1


def test_pending_call_error_message():
    """块内消费返回值抛 ParallelCallError 且消息含指引。"""
    client = Mock()
    client.execute.side_effect = [exist_result(True)]  # 退出块后 do_login 干净执行
    aw = DemoAW(client, make_user())

    with parallel():
        result = aw.do_login()

    with pytest.raises(Exception, match="封装进 AW 业务方法"):
        if result:
            pass


def test_nested_parallel_inside_aw_method():
    """AW 方法内部的 parallel() 块在执行线程内正常工作（设计 §4.7）。"""
    client = Mock()
    client.execute.side_effect = [click_result(), click_result()]
    aw = NestedAW(client, make_user())

    with parallel() as context:
        aw.do_double_click()

    assert len(context._tasks) == 1          # 外层只收集 do_double_click 一个任务
    assert client.execute.call_count == 2    # 内层块的两个点击在执行线程内执行


def test_api_aw_method_collected_and_runs():
    """API AW 业务方法同样被收集并在退出后执行。"""
    FakeApiAW.fetched.clear()
    api_aw = FakeApiAW(None, make_user(user_id="userA_api", platform="api"))

    with parallel() as context:
        api_aw.do_fetch()

    assert len(context._tasks) == 1
    assert context._tasks[0].user_id == "userA_api"
    assert FakeApiAW.fetched == [{"id": 1}]
