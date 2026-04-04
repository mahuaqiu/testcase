"""会议控制 AW。"""

from aw.base_aw import BaseAW


class MeetingControlAW(BaseAW):
    """Web 会议控制 AW。

    提供会议控制栏触发等操作。
    """

    PLATFORM = "web"

    def do_trigger_control_bar(self) -> dict:
        """触发会控栏显示。

        通过移动鼠标触发会控栏显示，然后等待挂断按钮出现。

        Returns:
            执行结果。
        """
        # 移动鼠标触发会控栏
        self.move(300, 300)

        # 等待挂断按钮出现
        return self.image_wait("images/web/会中_挂断.png")