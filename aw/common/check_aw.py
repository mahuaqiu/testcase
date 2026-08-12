"""公共检查 AW。"""

from typing import Dict, Optional

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

    def should_window_spec_exist(self, window_spec: Dict[str, str], process: str | None = None) -> bool:
        """检查窗口是否存在（仅 Windows 平台）。

        Args:
            window_spec: 窗口定位参数，如 {"class": "HwmMainWndClass"} 或 {"title": "华为云会议"}。
            process: 进程名（可选），如 'notepad.exe'，用于进一步过滤。

        Returns:
            True 如果窗口存在，False 如果不存在。
        """
        # 构建命令参数
        if "class" in window_spec:
            command = f'@tools/window-class-finder.exe --class="{window_spec["class"]}"'
        elif "title" in window_spec:
            command = f'@tools/window-class-finder.exe --title="{window_spec["title"]}"'
        else:
            raise ValueError("window_spec 必须包含 class 或 title 键")

        if process:
            command += f' --process="{process}"'

        result = self.cmd_exec(command)
        # stdout 在 actions[0] 中
        actions = result.get("actions", [])
        if not actions:
            return False
        stdout = actions[0].get("stdout", "").strip()
        return stdout != "null"