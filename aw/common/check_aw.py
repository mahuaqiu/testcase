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

    def should_window_class_exist(self, window_class: str, process: str | None = None) -> bool:
        """检查窗口类是否存在（仅 Windows 平台）。

        Args:
            window_class: 窗口类名，如 'Notepad'、'Chrome_WidgetWin_1'。
            process: 进程名（可选），如 'notepad.exe'，用于进一步过滤。

        Returns:
            True 如果窗口类存在，False 如果不存在。
        """
        # 使用 window-class-finder.exe 工具检查窗口类
        # stdout 为 "null" 表示窗口不存在，否则返回窗口信息 JSON
        command = f'@tools/window-class-finder.exe --class="{window_class}"'
        if process:
            command += f' --process="{process}"'

        result = self.cmd_exec(command)
        # stdout 在 actions[0] 中
        actions = result.get("actions", [])
        if not actions:
            return False
        stdout = actions[0].get("stdout", "").strip()
        return stdout != "null"