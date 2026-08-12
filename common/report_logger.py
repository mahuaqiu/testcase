"""报告日志收集器。"""

import sys
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional


class ReportLogger:
    """报告日志收集器。

    收集用例执行过程中的所有日志，用于生成 HTML 报告。
    每个用例一个实例，通过线程本地存储保证多线程安全。
    """

    _local = threading.local()

    # 需要显示的参数名（有意义的关键参数）
    _DISPLAY_ARGS = {
        "text", "label", "content", "image_path", "key", "url",
        "app_id", "x", "y", "from_x", "from_y", "to_x", "to_y",
        "duration_ms", "timeout", "index", "confidence"
    }

    # 不显示的参数名（内部参数或 base64）
    _HIDDEN_ARGS = {
        "platform", "user_id", "user_account", "user_name",
        "target_image", "image_base64", "screenshot"
    }

    @classmethod
    def get_current(cls) -> "ReportLogger":
        """获取当前线程的日志收集器。"""
        if not hasattr(cls._local, "logger"):
            cls._local.logger = cls()
        return cls._local.logger

    @classmethod
    def reset(cls) -> None:
        """重置当前线程的日志收集器。"""
        cls._local.logger = cls()

    def __init__(self):
        self._logs: List[Dict[str, Any]] = []
        self._start_time = datetime.now()
        self._lock = threading.Lock()
        self._last_failed_aw: Optional[Dict[str, Any]] = None  # 追踪最后失败的 AW

    def _filter_display_args(self, args: dict) -> dict:
        """过滤参数，只保留需要显示的。

        Args:
            args: 原始参数字典。

        Returns:
            过滤后的参数字典，只包含需要显示的参数。
        """
        return {
            k: v for k, v in args.items()
            if k in self._DISPLAY_ARGS and k not in self._HIDDEN_ARGS
        }

    def _format_args(self, args: dict) -> str:
        """格式化参数为字符串。

        Args:
            args: 参数字典。

        Returns:
            格式化后的参数字符串，如 "text=\"登录\", timeout=5"。
        """
        if not args:
            return ""
        parts = []
        for k, v in args.items():
            # 字符串值加引号，其他值直接显示
            if isinstance(v, str):
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts)

    def log_step(self, step: str, detail: str = "") -> None:
        """记录测试步骤。

        Args:
            step: 步骤名称。
            detail: 步骤详情（可选）。
        """
        with self._lock:
            self._logs.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "step",
                "step": step,
                "detail": detail
            })
        # 控制台输出（使用 stderr 绕过 pytest 输出捕获，实时显示）
        time_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        if detail:
            # 有详情时，打印详情（如资源申请的 JSON）
            sys.stderr.write(f"{time_str} 步骤: {step}\n{detail}\n")
        else:
            sys.stderr.write(f"{time_str} 步骤: {step}\n")
        sys.stderr.flush()

    def log_aw_message(
        self,
        message: str,
        aw_name: str = "",
        user_id: str = "",
        user_account: str = "",
        user_name: str = "",
        user_ip: str = "",
        user_platform: str = "",
        parent_aw: str = "",
        parent_call_id: str = "",
        parent_display: str = "",
        level: str = "info",
    ) -> None:
        """记录 AW 内的自定义日志，并归入当前业务方法步骤。

        Args:
            message: 要展示的日志内容。
            aw_name: 当前 AW 类名。
            user_id: 用户标识。
            user_account: 用户账号。
            user_name: 用户姓名。
            user_ip: Worker IP 地址。
            user_platform: 用户实际设备类型。
            parent_aw: 当前业务方法标识。
            parent_call_id: 当前业务方法调用 ID。
            parent_display: 当前业务方法显示名。
            level: 日志级别，info / warning / error，默认 info。
                在 HTML 报告中按级别用不同颜色展示。
        """
        log_entry = {
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "type": "aw_log",
            "aw_name": aw_name,
            "method": parent_aw.rsplit(".", 1)[-1] if parent_aw else "log",
            "message": str(message),
            "level": level if level in ("info", "warning", "error") else "info",
            "args": {
                "user_id": user_id,
                "user_account": user_account,
                "user_name": user_name,
                "user_ip": user_ip,
                "user_platform": user_platform,
            },
            "success": True,
            "parent_aw": parent_aw,
            "parent_call_id": parent_call_id,
            "parent_display": parent_display,
        }
        with self._lock:
            self._logs.append(log_entry)

        # 保留实时控制台输出，便于定位正在执行的用例。
        time_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = f"{aw_name} 日志" if aw_name else "日志"
        sys.stderr.write(f"{time_str} {prefix}: {message}\n")
        sys.stderr.flush()

    def log_aw_call(
        self,
        aw_name: str,
        method: str,
        args: dict,
        success: bool,
        result: dict,
        duration_ms: int,
        target_image: str = "",
        target_image_path: str = "",
        parent_aw: str = "",  # 父级 AW 标识
        is_business_method: bool = False,  # 是否是业务方法日志
        request_id: str = "",  # worker action 的 request_id
        call_id: str = "",  # 业务方法本次调用的唯一 ID
        parent_call_id: str = "",  # 所属父级业务方法调用的唯一 ID
        display_name: str = "",  # 业务方法显示名（docstring 首行）
        parent_display: str = ""  # 父级业务方法显示名
    ) -> None:
        """记录 AW 方法调用。

        Args:
            aw_name: AW 类名。
            method: 方法名。
            args: 调用参数。
            success: 是否成功。
            result: 执行结果。
            duration_ms: 执行耗时（毫秒）。
            target_image: 目标图片的 base64 编码（仅 image_* 操作失败时有值）。
            target_image_path: 目标图片路径（仅 image_* 操作失败时有值）。
            parent_aw: 父级 AW 标识，格式为 "LoginAW.do_login"，表示该原子操作属于哪个业务方法。
            is_business_method: 是否是业务方法日志（用于区分业务方法和原子操作）。
            request_id: worker action 的请求 ID，用于定位问题。
            call_id: 业务方法本次调用的唯一 ID，同名方法多次调用可区分。
            parent_call_id: 所属父级业务方法调用的唯一 ID，报告据此精确分组。
            display_name: 业务方法显示名（docstring 首行），报告标题自动使用。
            parent_display: 父级业务方法显示名，用于缺失父日志时重建分组标题。
        """
        with self._lock:
            log_entry = {
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "aw_call",
                "aw_name": aw_name,
                "method": method,
                "args": args,
                "success": success,
                "result": result,
                "duration_ms": duration_ms,
                "target_image": target_image,
                "target_image_path": target_image_path,
                "parent_aw": parent_aw,
                "is_business_method": is_business_method,  # 新增
                "request_id": request_id,  # 新增
                "call_id": call_id,
                "parent_call_id": parent_call_id,
                "display_name": display_name,
                "parent_display": parent_display
            }
            self._logs.append(log_entry)
            # 追踪失败的 AW 调用
            if not success:
                self._last_failed_aw = log_entry

        # 控制台输出（使用 stderr 绕过 pytest 输出捕获，实时显示）
        # 业务方法日志不输出（避免重复）
        if not is_business_method:
            display_args = self._filter_display_args(args)
            args_str = self._format_args(display_args)
            status_icon = "✓" if success else "✗"
            time_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            if args_str:
                sys.stderr.write(f"{time_str} {aw_name}.{method}({args_str}) {status_icon} {duration_ms}ms\n")
            else:
                sys.stderr.write(f"{time_str} {aw_name}.{method}() {status_icon} {duration_ms}ms\n")
            sys.stderr.flush()

    def log_worker_call(
        self,
        api: str,
        params: dict,
        success: bool,
        response: dict,
        duration_ms: int
    ) -> None:
        """记录 Worker HTTP 调用。"""
        with self._lock:
            self._logs.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "worker_call",
                "api": api,
                "params": params,
                "success": success,
                "response": response,
                "duration_ms": duration_ms
            })

    def log_screenshot(self, user_id: str, base64_data: str) -> None:
        """记录失败截图（base64）。"""
        with self._lock:
            self._logs.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "screenshot",
                "user_id": user_id,
                "base64": base64_data
            })

    def log_error(self, error: str, user_id: Optional[str] = None) -> None:
        """记录错误信息。

        Args:
            error: 错误信息。
            user_id: 报错用户ID（可选，用于报告跟随用户显示）。
        """
        with self._lock:
            log_entry = {
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "error",
                "error": error
            }
            if user_id:
                log_entry["user_id"] = user_id
            self._logs.append(log_entry)

    def get_logs(self) -> List[Dict[str, Any]]:
        """获取所有日志。"""
        with self._lock:
            return self._logs.copy()

    def get_duration(self) -> int:
        """获取执行时长（毫秒）。"""
        return int((datetime.now() - self._start_time).total_seconds() * 1000)

    def get_last_failed_aw(self) -> Optional[Dict[str, Any]]:
        """获取最后失败的 AW 调用信息。"""
        with self._lock:
            return self._last_failed_aw

    def is_api_failure(self) -> bool:
        """判断失败是否来自 API AW。

        通过检查失败 AW 调用的 user_id 是否以 _api 结尾来判断。

        Returns:
            True 表示 API AW 失败，False 表示普通 AW 失败或无失败。
        """
        with self._lock:
            if not self._last_failed_aw:
                return False
            args = self._last_failed_aw.get("args", {})
            user_id = args.get("user_id", "")
            return user_id.endswith("_api")
