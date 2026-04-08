"""
 # 测试用例： 会议等候室功能

 ## 前置条件：
 1.api预约会议，并开启等候室
 2. webrtc端主持人A，webrtc端与会者B, 都已登录

 ## 测试步骤与预期
 - STEP 1. WEBRTC主持人、与会者B入会
 	- EXPECT: 主持人入会成功，与会者B进入等候室
 - STEP 2. 主持人准入与会者B
 	- EXPECT: 主持人准入成功，与会者B加入会议成功
 - STEP 3. portal设置关闭等候室，与会者B离会后重新入会
 	- EXPECT: 与会者B再次入会成功，没有进入等候室
 - STEP 4. portal设置开启等候室，与会者B离会后重新入会
 	- EXPECT: 与会者B再次入会,进入等候室
 - STEP 5. 主持人准入与会者B
 	- EXPECT: 主持人准入成功，与会者B加入会议成功

 ## 清理步骤
1. api取消会议
2. 关掉浏览器

## 用例归属
1. web端
2. 目录：testcases\web\waitingroom
"""
import pytest
from common.parallel import parallel


@pytest.mark.users({"userA": "web","userB": "web"})
class TestClass:

    def test_waitingroom_switch_001(self, users):
        """会议等候室功能。"""
        userA = users["userA"]
        userB = users["userB"]
        userA_api = users["userA_api"]

        # webrtc端主持人A，webrtc端与会者B, 都已登录
        with parallel():
            userA.do_login()
            userB.do_login()
            userA.should_login_success()
            userB.should_login_success()

        # api预约会议，并开启等候室
        meeting = userA_api.do_create_meeting(
            subject="会议等候室功能",
            waiting_room=True
        )

        # STEP 1. WEBRTC主持人、与会者B入会
        # EXPECT: 主持人入会成功，与会者B进入等候室
        userA.do_join_as_host(meeting)
        userA.should_join_success(number=1)

        userB.do_join_as_guest(meeting)
        userB.should_in_waitingroom()

        #STEP 2. 主持人准入与会者B
 	    #EXPECT: 主持人准入成功，与会者B加入会议成功
        userA.do_admit_participant(userB.name)
        userB.should_join_success(number=2)

        #STEP 3. portal设置关闭等候室，与会者B离会后重新入会
 	    #EXPECT: 与会者B再次入会成功，没有进入等候室
        userA_api.do_set_waiting_room(conference_id=meeting.conference_id,
                                      chair_password=meeting.chair_password,
                                      enable=False)
        userB.do_leave()
        userB.do_join_as_guest(meeting)
        userB.should_join_success(number=2)

        #STEP 4. portal设置开启等候室，与会者B离会后重新入会
 	    #EXPECT: 与会者B再次入会,进入等候室
        userA_api.do_set_waiting_room(conference_id=meeting.conference_id,
                                      chair_password=meeting.chair_password,
                                      enable=False)
        userB.do_leave()
        userB.do_join_as_guest(meeting)
        userB.should_in_waitingroom()

        #STEP 5. 主持人准入与会者B
 	    #EXPECT: 主持人准入成功，与会者B加入会议成功
        userA.do_admit_participant(userB.name)
        userB.should_join_success(number=2)




