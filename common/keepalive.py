"""保活线程管理器。"""

import threading
import time
from typing import Dict, Any

import requests


class KeepAliveManager:
    """保活管理器。

    后台线程每 30 秒调用一次 /env/keepalive。
    超过 2 分钟不调用，worker 会被释放。
    """

    INTERVAL = 30  # 保活间隔（秒）

    def __init__(self, base_url: str, timeout: int = 30):
        """初始化保活管理器。

        Args:
            base_url: 资源管理服务地址。
            timeout: 请求超时时间。
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()
        self._resources: Dict[str, Any] = {}

    def start(self, resources: Dict[str, Any]) -> None:
        """启动保活线程。

        Args:
            resources: 申请到的用户资源 JSON（用于 keepalive 请求）。
        """
        if self._thread and self._thread.is_alive():
            return  # 已在运行

        self._resources = resources
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止保活线程。"""
        if not self._thread:
            return

        self._stop_event.set()
        self._thread.join(timeout=5)  # 等待线程结束
        self._thread = None
        self._resources = {}

    def _run(self) -> None:
        """保活线程主循环。"""
        while not self._stop_event.is_set():
            try:
                # 构建 EnvMachineIdItem 列表
                machine_ids = [
                    {"id": user_data.get("id")}
                    for user_data in self._resources.values()
                    if user_data.get("id")
                ]
                if machine_ids:
                    url = f"{self._base_url}/env/keepusing"
                    requests.post(url, json=machine_ids, timeout=self._timeout)
            except Exception:
                pass  # 保活失败不阻塞

            # 每 30 秒执行一次，可被 stop_event 中断
            self._stop_event.wait(self.INTERVAL)