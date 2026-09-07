"""运行时全局状态测试。"""

from common import runtime


def test_exe_param_roundtrip():
    """set_exe_param 写入后 get_exe_param 应返回同一字典。"""
    runtime.set_exe_param({"env": "prod", "namespace": "web_public"})

    assert runtime.get_exe_param() == {"env": "prod", "namespace": "web_public"}

    runtime.set_exe_param({})


def test_set_exe_param_treats_none_as_empty():
    """set_exe_param(None) 应归一为空字典。"""
    runtime.set_exe_param(None)

    assert runtime.get_exe_param() == {}


def test_conftest_reexports_runtime_accessors():
    """根 conftest 应再导出 get_config/get_exe_param，存量引用不炸。"""
    import conftest

    assert conftest.get_exe_param is runtime.get_exe_param
    assert conftest.get_config is runtime.get_config
