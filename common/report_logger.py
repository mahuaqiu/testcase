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
        sys.stderr.write(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} 步骤: {step}\n")
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
        is_business_method: bool = False  # 是否是业务方法日志
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
                "is_business_method": is_business_method  # 新增
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

    def log_error(self, error: str) -> None:
        """记录错误信息。"""
        with self._lock:
            self._logs.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "error",
                "error": error
            })

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