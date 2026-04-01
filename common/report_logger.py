"""报告日志收集器。"""

import threading
from datetime import datetime
from typing import Dict, List, Any, Optional


class ReportLogger:
    """报告日志收集器。

    收集用例执行过程中的所有日志，用于生成 HTML 报告。
    每个用例一个实例，通过线程本地存储保证多线程安全。
    """

    _local = threading.local()

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

    def log_step(self, step: str, detail: str = "") -> None:
        """记录测试步骤。"""
        with self._lock:
            self._logs.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "step",
                "step": step,
                "detail": detail
            })

    def log_aw_call(
        self,
        aw_name: str,
        method: str,
        args: dict,
        success: bool,
        result: dict,
        duration_ms: int,
        target_image: str = "",
        target_image_path: str = ""
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
                "target_image_path": target_image_path
            }
            self._logs.append(log_entry)
            # 追踪失败的 AW 调用
            if not success:
                self._last_failed_aw = log_entry

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