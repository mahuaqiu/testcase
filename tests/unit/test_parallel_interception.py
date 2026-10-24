"""AW 拦截点（收集模式）单元测试。"""

from unittest.mock import Mock

import pytest

from aw.api.base_api_aw import BaseApiAW
from aw.base_aw import BaseAW
from common.parallel import (
    CallTask,
    ParallelCallError,
    PendingCall,
    parallel,
)
from common.report_logger import ReportLogger


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


def test_get_text_in_block_raises_targeted_guidance():
    """块内顶层取文本调用抛带方法名与"取文本"指引的 ParallelCallError。"""
    client = Mock()
    aw = DemoAW(client, make_user())

    # raises 在块外：ParallelCallError 逃出 with 块，已收集任务不执行
    with pytest.raises(ParallelCallError, match=r"ocr_get_text[\s\S]*取文本"):
        with parallel():
            aw.ocr_get_text()

    assert client.execute.call_count == 0


def test_get_position_in_block_raises_targeted_guidance():
    """块内顶层取位置列表调用抛带方法名与"取列表"指引的 ParallelCallError。"""
    client = Mock()
    aw = DemoAW(client, make_user())

    with pytest.raises(ParallelCallError, match=r"ocr_get_position[\s\S]*取列表"):
        with parallel():
            aw.ocr_get_position("登录")

    assert client.execute.call_count == 0


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


def _run_and_collect_aw_call_logs(run):
    """重置当前线程 ReportLogger 后执行 run，返回收集到的 aw_call 日志条目。"""
    ReportLogger.reset()
    run()
    return [
        entry for entry in ReportLogger.get_current().get_logs()
        if entry.get("type") == "aw_call"
    ]


def test_parallel_business_method_logs_grouped_like_sequential():
    """并行块内业务方法的报告分组与顺序执行一致（业务条目+parent_call_id 归组）。"""
    # 并行执行：do_login 内部 ocr_exist(False) → 走 ocr_click 分支
    parallel_client = Mock()
    parallel_client.execute.side_effect = [exist_result(False), click_result()]
    parallel_aw = DemoAW(parallel_client, make_user())
    entries = _run_and_collect_aw_call_logs(lambda: _run_parallel_do_login(parallel_aw))

    # 1) 并行路径存在 method=='do_login' 的业务方法条目（is_business_method 标记）
    business = [
        e for e in entries
        if e["method"] == "do_login" and e["is_business_method"]
    ]
    assert business, "并行路径缺少 do_login 业务方法日志条目（报告卡片消失）"
    business_entry = business[0]
    assert business_entry["call_id"] != ""

    # 2) 并行路径的 ocr_click 原子条目 parent_call_id 非空，且等于业务条目的 call_id
    click_entries = [e for e in entries if e["method"] == "ocr_click"]
    assert click_entries, "并行路径缺少 ocr_click 原子操作日志条目"
    assert click_entries[0]["parent_call_id"] != "", (
        "并行路径原子条目 parent_call_id 为空（全落'直接操作'分组）"
    )
    assert click_entries[0]["parent_call_id"] == business_entry["call_id"]
    assert click_entries[0]["parent_aw"] == "DemoAW.do_login"

    # 3) 顺序基线同样结构（对照断言，证明"与顺序执行一致"）
    sequential_client = Mock()
    sequential_client.execute.side_effect = [exist_result(False), click_result()]
    sequential_aw = DemoAW(sequential_client, make_user())
    seq_entries = _run_and_collect_aw_call_logs(
        lambda: sequential_aw.do_login()
    )
    seq_business = [
        e for e in seq_entries
        if e["method"] == "do_login" and e["is_business_method"]
    ]
    assert seq_business and seq_business[0]["call_id"] != ""
    seq_click = [e for e in seq_entries if e["method"] == "ocr_click"]
    assert seq_click and seq_click[0]["parent_call_id"] == seq_business[0]["call_id"]
    assert seq_click[0]["parent_aw"] == "DemoAW.do_login"

    # 两条路径的 (method, is_business_method, parent_aw) 结构序列完全一致
    def structural_signature(logs):
        return [(e["method"], e["is_business_method"], e["parent_aw"]) for e in logs]

    assert structural_signature(entries) == structural_signature(seq_entries)


def _run_parallel_do_login(aw):
    """在 parallel 块内调用业务方法（执行线程内真实运行）。"""
    with parallel():
        aw.do_login()
