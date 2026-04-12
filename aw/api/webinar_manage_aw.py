"""网络研讨会管理 API 操作封装。

封装创建、取消、查询网络研讨会等操作。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List

from aw.api.base_api_aw import BaseApiAW, ApiError
from variable.manage_var import ManageVar


@dataclass
class WebinarInfo:
    """网络研讨会信息。"""
    conference_id: str        # 研讨会 ID
    chair_pwd: str            # 主持人密码
    guest_pwd: str            # 来宾密码
    audience_pwd: str         # 观众密码
    chair_join_uri: str       # 主持人入会链接
    guest_join_uri: str       # 与会者入会链接
    audience_join_uri: str    # 观众入会链接
    subject: str              # 研讨会主题
    begin_time: str           # 开始时间
    duration: int             # 时长（分钟）
    vmr_id: str               # VMR ID
    vmr_pkg_name: str         # 网络研讨会套餐名称


class WebinarManageAW(BaseApiAW):
    """网络研讨会管理 API 操作封装。

    封装华为云网络研讨会相关 API 操作。

    Args:
        user: User 实例，需包含 vmrID 属性（网络研讨会 VMR ID）。
    """

    _LOGIN_URL = ManageVar.LOGIN_URL

    # ── 业务方法 ─────────────────────────────────────────

    def do_create_webinar(self, subject: str, **kwargs) -> WebinarInfo:
        """创建网络研讨会。

        步骤: 登录 → 构造研讨会配置 → 调用创建接口 → 返回研讨会信息。

        Args:
            subject: 研讨会主题。
            **kwargs: 其他研讨会配置参数，如 beginTime、duration。

        Returns:
            WebinarInfo 实例，包含研讨会 ID、密码、入会链接等。

        Raises:
            ApiError: 创建失败时抛出。
        """
        # 构造研讨会配置（默认 beginTime/duration 在内部处理）
        body = self._build_webinar_body(subject, **kwargs)

        # 调用创建接口
        result = self._post(ManageVar.WEBINAR_URL, data=body)

        # 解析响应
        webinar_data = result.get("data", {})
        return self._parse_webinar_info(webinar_data)

    def do_cancel_webinar(self, conference_id: str) -> None:
        """取消指定网络研讨会。

        步骤: 登录 → 调用取消接口。

        Args:
            conference_id: 网络研讨会 ID。

        Raises:
            ApiError: 取消失败时抛出。
        """
        # 构造取消 URL（conferenceId 在 URL 路径中）
        cancel_url = f"{ManageVar.WEBINAR_URL}/{conference_id}"
        self._delete(cancel_url)

    def do_query_webinars(
        self,
        page_num: int = 1,
        page_size: int = 10,
        search_key: str = ""
    ) -> List[WebinarInfo]:
        """查询网络研讨会列表。

        步骤: 登录 → 调用查询接口 → 解析响应。

        Args:
            page_num: 页码，默认 1。
            page_size: 每页数量，默认 10。
            search_key: 搜索关键词，默认空。

        Returns:
            WebinarInfo 列表。

        Raises:
            ApiError: 查询失败时抛出。
        """
        body = {
            "pageNum": page_num,
            "pageSize": page_size,
            "searchKey": search_key,
            "joinMeetingType": "all"
        }

        result = self._post(ManageVar.WEBINAR_LIST_URL, data=body)

        # 解析响应
        webinars = []
        data = result.get("data", {})
        webinar_list = data.get("list", [])
        for webinar_data in webinar_list:
            webinars.append(self._parse_webinar_info(webinar_data))

        return webinars

    def do_cancel_all_webinars(self) -> int:
        """取消所有网络研讨会。

        步骤: 查询研讨会列表 → 遍历取消每个研讨会。

        Returns:
            取消的研讨会数量。

        Raises:
            ApiError: 取消失败时抛出。
        """
        webinars = self.do_query_webinars(page_size=100)
        cancelled_count = 0

        for webinar in webinars:
            try:
                self.do_cancel_webinar(webinar.conference_id)
                cancelled_count += 1
            except ApiError:
                # 单个取消失败不中断整体流程
                pass

        return cancelled_count

    # ── 内部方法 ─────────────────────────────────────────

    def _build_webinar_body(self, subject: str, **kwargs) -> Dict[str, Any]:
        """构造创建网络研讨会请求体。

        Args:
            subject: 研讨会主题。
            **kwargs: 其他配置，如 beginTime、duration。

        Returns:
            请求体字典。
        """
        # 从 kwargs 中提取 beginTime 和 duration，没有则使用默认值
        begin_time = kwargs.pop("beginTime", None)
        duration = kwargs.pop("duration", 120)

        # 默认开始时间：当前时间 + 5 分钟
        if not begin_time:
            start_dt = datetime.now() + timedelta(minutes=5)
            begin_time = start_dt.strftime("%Y-%m-%d %H:%M")

        # 获取 vmrID（从 user 扩展属性）
        vmr_id = getattr(self.user, "vmrID", "") if self.user else ""
        if not vmr_id:
            raise ApiError("create_webinar", 0, "user 缺少 vmrID 属性")

        # 获取用户信息（用于 attendees）
        user_id = self._get_user_uuid()
        user_name = self.user.name if self.user else ""
        user_account = self.user.account if self.user else ""
        dept_name = getattr(self.user, "deptName", "集体测试") if self.user else "集体测试"
        sip = getattr(self.user, "sip", "") if self.user else ""

        body = {
            "beginTime": begin_time,
            "subject": subject,
            "duration": duration,
            "timeZoneId": "56",
            "vmrID": vmr_id,
            "vmrPkgAudienceParties": 3000,
            "vmrPkgName": "网络研讨会7818",
            "attendees": [
                {
                    "userId": user_id,
                    "userName": user_name,
                    "sms": None,
                    "sip": sip,
                    "deptName": dept_name,
                    "phone": None,
                    "userAccount": user_account,
                    "email": None,
                    "type": "NORMAL_USER"
                }
            ],
            "notifySetting": {
                "enableEmail": "N",
                "enableCalendar": "N",
                "enableSms": "N"
            },
            "supportSimultaneousInterpretation": False,
            "confExtendProperties": [
                {"propertyKey": "supportWatermark", "propertyValue": "false"}
            ],
            "liveChannelID": "",
            "conferenceType": 0,
            "callRestriction": False,
            "enableRecording": "N",
            "recordType": 2,
            "guestPasswd": None,
            "audiencePasswd": None,
            "audienceScope": 0,
            "scope": 0,
            "vmrFlag": 1
        }

        # 合并其他额外配置
        body.update(kwargs)

        return body

    def _parse_webinar_info(self, data: Dict[str, Any]) -> WebinarInfo:
        """解析网络研讨会信息响应。

        Args:
            data: API 响应数据。

        Returns:
            WebinarInfo 实例。
        """
        return WebinarInfo(
            conference_id=data.get("conferenceId", ""),
            chair_pwd=data.get("chairPasswd", ""),
            guest_pwd=data.get("guestPasswd", ""),
            audience_pwd=data.get("audiencePasswd", ""),
            chair_join_uri=data.get("chairJoinUri", ""),
            guest_join_uri=data.get("guestJoinUri", ""),
            audience_join_uri=data.get("audienceJoinUri", ""),
            subject=data.get("subject", ""),
            begin_time=data.get("beginTime", ""),
            duration=data.get("duration", 0),
            vmr_id=data.get("vmrID", ""),
            vmr_pkg_name=data.get("vmrPkgName", "")
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