"""会议管理 API 操作封装。

封装登录、预约会议、取消会议、查询会议列表等操作。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from aw.api.base_api_aw import BaseApiAW, ApiError
from variable.manage_var import ManageVar


@dataclass
class MeetingInfo:
    """会议信息。"""
    conference_id: str        # 会议 ID
    chair_pwd: str           # 主持人密码
    guest_pwd: str           # 来宾密码
    chair_join_uri: str      # 主持人入会链接
    guest_join_uri: str      # 与会者入会链接
    subject: str             # 会议主题
    start_time: str          # 开始时间
    end_time: str            # 结束时间
    user_uuid: str           # 用户 UUID


class MeetingManageAW(BaseApiAW):
    """会议管理 API 操作封装。

    封装华为云会议管理相关 API 操作。

    Args:
        user: User 实例。
    """

    _LOGIN_URL = ManageVar.LOGIN_URL

    # ── 业务方法 ─────────────────────────────────────────

    def do_login(self) -> None:
        """显式登录获取 token。

        通常无需调用，其他方法会自动登录。
        """
        self._login()

    def do_create_meeting(
        self,
        subject: str,
        start_time: Optional[str] = None,
        length: int = 60,
        guest_pwd: Optional[str] = None,
        **kwargs
    ) -> MeetingInfo:
        """预约/创建会议。

        步骤: 登录 → 构造会议配置 → 调用创建接口 → 返回会议信息。

        Args:
            subject: 会议主题。
            start_time: 开始时间，格式 "YYYY-MM-DD HH:MM"，默认当前时间+5分钟。
            length: 会议时长（分钟），默认 60。
            guest_pwd: 来宾密码，不填则自动生成。
            **kwargs: 其他会议配置参数。

        Returns:
            MeetingInfo 实例，包含会议 ID、密码、入会链接等。

        Raises:
            ApiError: 创建失败时抛出。
        """
        # 默认开始时间：当前时间 + 5 分钟
        if not start_time:
            start_dt = datetime.now() + timedelta(minutes=5)
            start_time = start_dt.strftime("%Y-%m-%d %H:%M")

        # 构造会议配置
        body = self._build_meeting_body(subject, start_time, length, guest_pwd, **kwargs)

        # 调用创建接口
        result = self._post(ManageVar.CONFERENCE_URL, data=body)

        # 解析响应
        if isinstance(result, list) and len(result) > 0:
            meeting_data = result[0]
        else:
            meeting_data = result

        return self._parse_meeting_info(meeting_data)

    def do_cancel_meeting(self, conference_id: str) -> None:
        """取消指定会议。

        步骤: 登录 → 调用取消接口。

        Args:
            conference_id: 会议 ID。

        Raises:
            ApiError: 取消失败时抛出。
        """
        params = {"conferenceID": conference_id, "type": 1}
        self._delete(ManageVar.CONFERENCE_URL, params=params)

    def do_query_meetings(self, limit: int = 10) -> List[MeetingInfo]:
        """查询我的会议列表。

        步骤: 登录 → 调用查询接口 → 解析响应。

        Args:
            limit: 返回数量限制，默认 10。

        Returns:
            MeetingInfo 列表。

        Raises:
            ApiError: 查询失败时抛出。
        """
        # 获取 user_uuid
        user_uuid = self._get_user_uuid()

        params = {
            "userUUID": user_uuid,
            "offset": 0,
            "limit": limit,
            "queryAll": "false",
            "searchKey": "",
            "queryConfMode": "ALL"
        }
        result = self._get(ManageVar.CONFERENCE_URL, params=params)

        meetings = []
        # API 返回 {"data": [...], "count": N} 结构
        meeting_list = result.get("data", []) if isinstance(result, dict) else result
        if isinstance(meeting_list, list):
            for meeting_data in meeting_list:
                meetings.append(self._parse_meeting_info(meeting_data))

        return meetings

    def do_cancel_all_meetings(self) -> int:
        """取消所有会议。

        步骤: 查询会议列表 → 遍历取消每个会议。

        Returns:
            取消的会议数量。

        Raises:
            ApiError: 取消失败时抛出。
        """
        meetings = self.do_query_meetings(limit=100)
        cancelled_count = 0

        for meeting in meetings:
            try:
                self.do_cancel_meeting(meeting.conference_id)
                cancelled_count += 1
            except ApiError:
                # 单个取消失败不中断整体流程
                pass

        return cancelled_count

    # ── 内部方法 ─────────────────────────────────────────

    def _build_meeting_body(
        self,
        subject: str,
        start_time: str,
        length: int,
        guest_pwd: Optional[str],
        **kwargs
    ) -> Dict[str, Any]:
        """构造创建会议请求体。

        Args:
            subject: 会议主题。
            start_time: 开始时间。
            length: 时长（分钟）。
            guest_pwd: 来宾密码。
            **kwargs: 其他配置。

        Returns:
            请求体字典。
        """
        body = {
            "startTime": start_time,
            "timeZoneID": "52",
            "vmrID": None,
            "userVmrId": None,
            "isAutoRecord": 0,
            "picLayouts": [],
            "picDisplay": {},
            "interpreterGroups": [],
            "autoSimultaneousInterpretation": True,
            "supportSimultaneousInterpretation": False,
            "subject": subject,
            "language": "zh-CN",
            "mediaTypes": "Data,HDVideo,Voice",
            "conferenceType": 0,
            "recordType": 2,
            "recordAuxStream": 1,
            "confConfigInfo": {
                "vmrIDType": 1,
                "isGuestFreePwd": False,
                "callInRestriction": 0,
                "isSendSms": False,
                "isSendCalendar": False,
                "defaultSummaryState": 0,
                "enableWaitingRoom": False,
                "supportWaitingRoom": True,
                "allowGuestStartConf": True,
                "isKeyAssuranceConf": False,
                "isShowSettingTips": False,
                "joinBeforeHostTime": 10,
                "connectorCallInRestriction": 0,
                "highResolutionMode": 0,
                "isSendNotify": False,
                "confExtendProperties": [
                    {"propertyKey": "enableVideo4k", "propertyValue": "false"},
                    {"propertyKey": "autoPublishSummary", "propertyValue": "false"},
                    {"propertyKey": "forbiddenScreenShots", "propertyValue": "false"},
                    {"propertyKey": "supportWatermark", "propertyValue": "false"}
                ]
            },
            "attendees": [],
            "length": length,
            "vmrFlag": 0
        }

        # 设置来宾密码
        if guest_pwd:
            body["confConfigInfo"]["guestPwd"] = guest_pwd

        # 合并额外配置
        body.update(kwargs)

        return body

    def _parse_meeting_info(self, data: Dict[str, Any]) -> MeetingInfo:
        """解析会议信息响应。

        Args:
            data: API 响应数据。

        Returns:
            MeetingInfo 实例。
        """
        # 解析密码
        chair_pwd = ""
        guest_pwd = ""
        for pwd_entry in data.get("passwordEntry", []):
            if pwd_entry.get("conferenceRole") == "chair":
                chair_pwd = pwd_entry.get("password", "")
            elif pwd_entry.get("conferenceRole") == "general":
                guest_pwd = pwd_entry.get("password", "")

        return MeetingInfo(
            conference_id=data.get("conferenceID", ""),
            chair_pwd=chair_pwd,
            guest_pwd=guest_pwd,
            chair_join_uri=data.get("chairJoinUri", ""),
            guest_join_uri=data.get("guestJoinUri", ""),
            subject=data.get("subject", ""),
            start_time=data.get("startTime", ""),
            end_time=data.get("endTime", ""),
            user_uuid=data.get("userUUID", "")
        )

    def _get_user_uuid(self) -> str:
        """获取用户 UUID。

        从登录响应或缓存中获取 user_uuid。
        如果没有，先触发登录。

        Returns:
            user_uuid 字符串。

        Raises:
            ApiError: 无法获取 user_uuid 时抛出。
        """
        # 确保 token 有效
        self._ensure_token()

        # 从 token_info 中获取
        if self._token_info and self._token_info.user_uuid:
            return self._token_info.user_uuid

        # 如果 token_info 中没有 user_uuid，抛出异常
        raise ApiError("get_user_uuid", 0, "无法获取 user_uuid，请检查登录响应")