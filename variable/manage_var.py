"""会议管理 API URL 常量。"""


class ManageVar:
    """会议管理 API 常量。"""

    # 基础 URL
    BASE_URL = "https://meeting.huaweicloud.com"

    # 登录接口
    LOGIN_URL = f"{BASE_URL}/v2/usg/acs/auth/account"

    # 会议管理接口
    CONFERENCE_URL = f"{BASE_URL}/v1/mmc/management/conferences"

    # 会议站点信息接口
    REGION_INFO_URL = f"{BASE_URL}/v1/mmc/management/conferences/region/random"