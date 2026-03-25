"""会议等候室入会测试用例。

测试场景: 验证等候室开启/关闭场景下的入会流程
"""

import pytest

from aw.api.meeting_manage_aw import MeetingInfo


@pytest.mark.users({"host": "web", "participant": "web"})
class TestWaitingroomJoin:
    """会议等候室入会测试。"""

    def test_execute(self, users):
        """执行测试：等候室场景入会测试。"""
        # 获取用户资源
        host = users["host"]              # 主持人（UI）
        participant = users["participant"]  # 与会者A（UI）
        host_api = users["host_api"]      # 主持人（API，自动创建）

        # 前置：API 预约会议并开启等候室
        meeting = host_api.do_create_meeting(
            subject="等候室测试会议",
            confConfigInfo={"enableWaitingRoom": True}
        )

        # STEP 1: 主持人、与会者A入会
        host.do_join_as_host(meeting)
        host.should_join_success()

        participant.do_join_as_guest(meeting)
        participant.should_in_waitingroom()

        # STEP 2: 主持人准入与会者A
        host.do_admit_participant()
        participant.should_join_success()

        # STEP 3: portal设置关闭等候室，与会者A离会后再重新入会
        host_api.do_set_waiting_room(
            conference_id=meeting.conference_id,
            chair_password=meeting.chair_pwd,
            enable=False
        )
        participant.do_leave()
        participant.do_join_as_guest(meeting)
        participant.should_join_success()  # 直接入会，不进等候室

        # STEP 4: portal设置开启等候室，与会者A离会后再重新入会
        host_api.do_set_waiting_room(
            conference_id=meeting.conference_id,
            chair_password=meeting.chair_pwd,
            enable=True
        )
        participant.do_leave()
        participant.do_join_as_guest(meeting)
        participant.should_in_waitingroom()  # 进入等候室

        # STEP 5: 主持人准入与会者A
        host.do_admit_participant()
        participant.should_join_success()

        # 清理：hooks 自动执行 stop_app 和 cancel_all_meetings