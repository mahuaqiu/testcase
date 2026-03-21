"""报告日志收集器。"""

import threading
from datetime import datetime
from typing import Dict, List, Any


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
        duration_ms: int
    ) -> None:
        """记录 AW 方法调用。"""
        with self._lock:
            self._logs.append({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": "aw_call",
                "aw_name": aw_name,
                "method": method,
                "args": args,
                "success": success,
                "result": result,
                "duration_ms": duration_ms
            })

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