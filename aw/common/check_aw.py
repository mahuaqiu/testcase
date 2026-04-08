"""公共检查 AW。"""

from aw.base_aw import BaseAW


class CheckAW(BaseAW):
    """公共检查操作封装。"""

    PLATFORM = "common"

    def should_toast_exists(self, text: str) -> dict:
        """断言toast提示文字存在。

        Args:
            text: 要验证的toast内容。
        """
        return self.ocr_assert(text)