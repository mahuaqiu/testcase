"""
公共模块。

提供测试工程通用的工具函数、断言、数据工厂和 testagent 客户端。
"""

from common.testagent_client import TestagentClient
from common.assertions import assert_response_ok, assert_json_contains
from common.data_factory import DataFactory

__all__ = [
    "TestagentClient",
    "assert_response_ok",
    "assert_json_contains",
    "DataFactory",
]