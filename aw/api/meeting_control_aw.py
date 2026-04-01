"""会议控制 API 操作封装。

封装等候室控制等会议中操作。
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from aw.api.base_api_aw import ApiError
from aw.api.meeting_manage_aw import MeetingManageAW
from variable.manage_var import ManageVar
import base64


@dataclass
class RegionInfo:
    """会议站点信息。"""
    region_ip: str    # 区域服务器地址
    uuid: str         # 会议 UUID


class MeetingControlAW(MeetingManageAW):
    """会议控制 API 操作封装。

    继承 MeetingManageAW，复用登录和 token 管理。
    提供等候室控制等会议中操作。

    Args:
        client: TestagentClient 实例（API AW 传 None）。
        user: User 实例，用于获取账号密码。
    """

    def __init__(self, client, user):
        """初始化会议控制 AW。

        Args:
            client: TestagentClient 实例（API AW 传 None）。
            user: User 实例。
        """
        super().__init__(client, user)
        self._region_info_cache: Dict[str, RegionInfo] = {}
        self._control_token_cache: Dict[str, str] = {}

    # ── 业务方法 ─────────────────────────────────────────

    def do_get_region_info(self, conference_id: str, chair_password: str) -> RegionInfo:
        """获取会议站点信息。

        步骤: 使用主持人密码调用站点信息接口 → 返回区域服务器地址。

        Args:
            conference_id: 会议 ID。
            chair_password: 主持人密码。

        Returns:
            RegionInfo 实例，包含区域服务器地址和 UUID。

        Raises:
            ApiError: 请求失败或响应数据异常时抛出。
        """
        # 检查缓存
        if conference_id in self._region_info_cache:
            return self._region_info_cache[conference_id]

        # 调用 API（使用主持人密码认证）
        headers = {
            "x-login-type": "1",
            "X-Password": chair_password
        }
        params = {"conferenceID": conference_id}
        result = self._get(ManageVar.REGION_INFO_URL, params=params, headers=headers, need_token=True)

        # 解析响应
        region_info = self._parse_region_info(result)

        # 缓存结果
        self._region_info_cache[conference_id] = region_info
        return region_info

    def do_get_control_token(self, conference_id: str, chair_password: str) -> str:
        """获取会议控制 token。

        步骤: 获取站点信息 → 调用 token 接口 → 返回控制 token。

        Args:
            conference_id: 会议 ID。
            chair_password: 主持人密码。

        Returns:
            会议控制 token 字符串。

        Raises:
            ApiError: 请求失败或响应数据异常时抛出。
        """
        # 检查缓存
        if conference_id in self._control_token_cache:
            return self._control_token_cache[conference_id]

        # 获取站点信息
        region_info = self.do_get_region_info(conference_id, chair_password)
        url = f"{self._get_region_base_url(region_info.region_ip)}/v1/mmc/control/conferences/token"

        # 调用 API（使用主持人密码认证，不需要登录 token）
        headers = {
            "x-login-type": "1",
            "X-Password": chair_password
        }
        params = {"conferenceID": conference_id}
        result = self._post_with_headers(url, data=None, headers=headers, params=params, need_token=False)

        # 解析响应
        token = result.get("data", {}).get("token", "")
        if not token:
            raise ApiError("get_control_token", 0, "未获取到控制 token")

        # 缓存结果
        self._control_token_cache[conference_id] = base64.b64encode(token.encode()).decode()
        return token

    def do_set_waiting_room(self, conference_id: str, chair_password: str, enable: bool) -> None:
        """设置等候室开关。

        步骤: 获取控制 token → 调用配置更新接口。

        Args:
            conference_id: 会议 ID。
            chair_password: 主持人密码。
            enable: True 开启等候室，False 关闭。

        Raises:
            ApiError: 请求失败时抛出。
        """
        # 获取站点信息和控制 token
        region_info = self.do_get_region_info(conference_id, chair_password)
        token = self.do_get_control_token(conference_id, chair_password)

        # 构造请求
        url = f"{self._get_region_base_url(region_info.region_ip)}/v1/mmc/control/conferences/updateStartedConfConfig"
        headers = {
            "x-conference-authorization": f"Basic {token}"
        }
        params = {"conferenceID": conference_id}
        body = {"enableWaitingRoom": 1 if enable else 0}

        # 调用 API（使用控制 token 认证，不需要登录 token）
        self._put(url, data=body, headers=headers, params=params, need_token=False)

    # ── 内部方法 ─────────────────────────────────────────

    def _get_region_base_url(self, region_ip: str) -> str:
        """构造区域服务器基础 URL。

        Args:
            region_ip: 区域服务器地址。

        Returns:
            完整的 HTTPS URL。
        """
        return f"https://{region_ip}"

    def _parse_region_info(self, data: Dict[str, Any]) -> RegionInfo:
        """解析站点信息响应。

        Args:
            data: API 响应数据。

        Returns:
            RegionInfo 实例。

        Raises:
            ApiError: 关键字段为空时抛出。
        """
        region_ip = data.get("regionIP", "")
        uuid = data.get("uuid", "")

        if not region_ip:
            raise ApiError("parse_region_info", 0, "响应中缺少 regionIP 字段")
        if not uuid:
            raise ApiError("parse_region_info", 0, "响应中缺少 uuid 字段")

        return RegionInfo(region_ip=region_ip, uuid=uuid)