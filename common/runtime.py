"""运行时全局状态。

config / exeParam 的全局单例从根 conftest 迁到这里。用例、目录级
conftest 等一律从本模块导入，避免目录 conftest 与根 conftest 出现
模块名冲突后 `from conftest import get_exe_param` 解析到错误对象。
"""

from typing import Any, Dict

from common.config_loader import ConfigLoader

_config = None
_exe_param: Dict[str, Any] = {}


def get_config() -> Dict[str, Any]:
    """获取全局配置（单例）。"""
    global _config
    if _config is None:
        _config = ConfigLoader().load()
    return _config


def get_exe_param() -> Dict[str, Any]:
    """获取 exeParam 参数（解析后的 JSON 字典）。"""
    return _exe_param


def set_exe_param(exe_param: Dict[str, Any]) -> None:
    """写入 exeParam 参数（pytest_configure 解析后调用）。"""
    global _exe_param
    _exe_param = exe_param or {}
