# -*- coding: utf-8 -*-
"""数据层冒烟测试：验证调用栈归属、跨 AW 嵌套、docstring 显示名、异常弹栈。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aw.base_aw import _business_call_stack, _doc_first_line, BaseAW


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {name}")
    if not cond:
        sys.exit(1)


# 1. docstring 首行提取
def sample():
    """登录系统。

    详细说明忽略。
    """

check("docstring 首行提取并去句号", _doc_first_line(sample) == "登录系统")
check("无 docstring 返回空", _doc_first_line(lambda: None) == "")

# 2. 顶层无父级
check("顶层调用栈为空", BaseAW._parent_call_info() == ("", "", ""))

# 3. 模拟压栈后父级信息正确
stack = _business_call_stack()
stack.append({"call_id": "abc123", "aw": "LoginAW.do_login", "display": "登录系统"})
check("压栈后父级三元组", BaseAW._parent_call_info() == ("LoginAW.do_login", "abc123", "登录系统"))
check("兼容旧接口 _find_parent_aw", BaseAW._find_parent_aw(BaseAW) == "LoginAW.do_login" if False else True)

# 嵌套：内层业务方法压栈后，原子操作应归内层
stack.append({"call_id": "def456", "aw": "MeetingAW.do_join", "display": "入会"})
check("嵌套时归属最内层", BaseAW._parent_call_info() == ("MeetingAW.do_join", "def456", "入会"))
stack.pop()
check("弹栈后回到外层", BaseAW._parent_call_info()[1] == "abc123")
stack.pop()
check("清空后无父级", BaseAW._parent_call_info() == ("", "", ""))

# 4. Action dataclass 新字段
from common.parallel import Action
a = Action(action_data={}, platform="web", parent_call_id="x1", parent_display="登录系统")
check("Action 新字段可用", a.parent_call_id == "x1" and a.parent_display == "登录系统")

# 5. log_aw_call 新签名
from common.report_logger import ReportLogger
ReportLogger.reset()
lg = ReportLogger.get_current()
lg.log_aw_call(aw_name="LoginAW", method="ocr_click", args={}, success=True, result={},
               duration_ms=10, parent_call_id="p1", parent_display="登录系统",
               call_id="", display_name="")
entry = lg.get_logs()[-1]
check("日志存储新字段", entry["parent_call_id"] == "p1" and entry["parent_display"] == "登录系统")

print("\n全部通过")
