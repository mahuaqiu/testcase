"""KeepAliveManager 测试。"""

import time
import threading
import pytest
from unittest.mock import Mock, patch
from common.keepalive import KeepAliveManager


class TestKeepAliveManager:
    """KeepAliveManager 测试类。"""

    def test_start_creates_thread(self):
        """测试启动创建线程。"""
        manager = KeepAliveManager("http://localhost:8080", timeout=5)
        manager.start({"userA": {"ip": "127.0.0.1", "port": 8080}})

        assert manager._thread is not None
        assert manager._thread.is_alive()

        manager.stop()

    def test_stop_terminates_thread(self):
        """测试停止终止线程。"""
        manager = KeepAliveManager("http://localhost:8080", timeout=5)
        manager.start({"userA": {"ip": "127.0.0.1", "port": 8080}})

        manager.stop()

        # stop 后 _thread 被设置为 None，表示线程已停止
        assert manager._thread is None

    def test_keepalive_calls_api(self):
        """测试调用 keepalive API。"""
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200

            manager = KeepAliveManager("http://localhost:8080", timeout=5)
            resources = {"userA": {"ip": "127.0.0.1", "port": 8080}}

            manager.start(resources)
            time.sleep(0.5)  # 等待线程执行
            manager.stop()

            # 验证调用了 keepalive
            mock_post.assert_called()

    def test_double_start_is_safe(self):
        """测试重复启动是安全的。"""
        manager = KeepAliveManager("http://localhost:8080", timeout=5)
        manager.start({"userA": {"ip": "127.0.0.1", "port": 8080}})
        manager.start({"userA": {"ip": "127.0.0.1", "port": 8080}})  # 重复启动

        assert manager._thread.is_alive()
        manager.stop()