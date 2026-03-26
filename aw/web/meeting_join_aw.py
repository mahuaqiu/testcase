"""会议入会业务操作封装。

封装华为云会议 Web 端入会、离会、准入等操作。
"""

from typing import TYPE_CHECKING

from aw.base_aw import BaseAW
from aw.api.meeting_manage_aw import MeetingInfo

if TYPE_CHECKING:
    from common.user import User


class MeetingJoinAW(BaseAW):
    """会议入会业务操作封装。

    封装华为云会议 Web 端入会相关流程，包括主持人入会、与会者入会、离会、准入等操作。

    Args:
        client: TestagentClient 实例。
        user: 用户资源实例（可选），用于动态获取账号密码。
    """

    PLATFORM = "web"

    # ── 业务流程方法 ─────────────────────────────────────────

    def do_join_as_host(self, meeting: MeetingInfo) -> None:
        """主持人入会。

        步骤: 导航到主持人入会链接 → 等待入会页面加载 → 点击入会按钮。

        Args:
            meeting: 会议信息实例，包含主持人入会链接。
        """
        # 导航到主持人入会链接
        self.navigate(meeting.chair_join_uri)
        # 等待入会页面加载
        self.ocr_wait("加入会议", timeout=5000)
        # 点击加入会议按钮
        self.ocr_click("加入会议")

    def do_join_as_guest(self, meeting: MeetingInfo) -> None:
        """与会者入会。

        步骤: 导航到来宾入会链接 → 等待入会页面加载 → 点击入会按钮。

        Args:
            meeting: 会议信息实例，包含来宾入会链接。
        """
        # 导航到来宾入会链接
        self.navigate(meeting.guest_join_uri)
        # 等待入会页面加载
        self.ocr_wait("加入会议", timeout=5000)
        # 点击加入会议按钮
        self.ocr_click("加入会议")

    def do_leave(self) -> None:
        """离会。

        步骤: 点击离开按钮 → 确认离开。
        """
        # 点击离开按钮
        self.ocr_click("离开")
        # 确认离开（如有确认弹窗）
        self.ocr_click("确定")

    def do_admit_participant(self) -> None:
        """主持人准入与会者。

        步骤: 点击准入按钮（在等候室列表或弹窗中）。

        注意: 需要在主持人端执行，且等候室中有等待入会的与会者。
        """
        # 点击准入按钮
        self.ocr_click("准入")

    # ── 断言方法 ─────────────────────────────────────────────

    def should_join_success(self) -> None:
        """断言入会成功。

        验证入会后页面显示会议相关文字。
        """
        # 等待会议界面出现
        self.ocr_wait("离开", timeout=5000)

    def should_in_waitingroom(self) -> None:
        """断言用户在等候室中。

        验证等候室界面显示等待相关文字。
        """
        # 等待等候室界面出现
        self.ocr_wait("等待主持人准入", timeout=5000)

    def should_leave_success(self) -> None:
        """断言离会成功。

        验证离会后页面不再显示会议相关文字。
        """
        # 等待离开会议后的界面
        self.ocr_wait("我的会议", timeout=5000)