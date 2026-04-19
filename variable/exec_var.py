"""
固定运行命令常量定义。
"""


class ExecVar:
    """cmd_exec 动作常用命令模板。"""

    # PPT 播放命令（进入放映模式）
    PLAY_PPT = "powershell -ExecutionPolicy Bypass -File \"@tools/play_ppt.ps1\" -FilePath \"{ppt_path}\" -AutoPlay true"

    # PPT 打开命令（编辑模式）
    OPEN_PPT = "powershell -ExecutionPolicy Bypass -File \"@tools/play_ppt.ps1\" -FilePath \"{ppt_path}\" -AutoPlay false"

    # 进程检查命令
    CHECK_PROCESS = "powershell -ExecutionPolicy Bypass -File \"@tools/check_process.ps1\" -ProcessName \"{process_name}\""

    # 屏幕录制命令
    RECORD_SCREEN = "powershell -ExecutionPolicy Bypass -File \"@tools/record_screen.ps1\" -OutputPath \"{output_path}\" -Duration \"{duration}\""

    # 常用 PowerShell 命令
    # 获取进程列表
    GET_PROCESS_LIST = "powershell -Command \"Get-Process | Select-Object Name, Id, CPU | Format-Table\""

    # 杀掉指定进程
    KILL_PROCESS = "powershell -Command \"Stop-Process -Name '{process_name}' -Force\""

    # 获取系统信息
    GET_SYSTEM_INFO = "powershell -Command \"Get-ComputerInfo | Select-Object OsName, OsVersion, WindowsVersion\""

    # Mac/Linux 常用命令
    # 查看文件列表
    LS_DIR = "ls -la {dir_path}"

    # 查看文件内容
    CAT_FILE = "cat {file_path}"

    # 查看进程
    PS_PROCESS = "ps aux | grep {process_name}"