"""伴生平台（web+windows）解析与懒 hooks 测试。"""

import pytest

from common.user import User
from common.users_marker import parse_users_requirement, validate_companion_platforms
from conftest import _build_keepalive_resources, _build_report_user_details


def test_parse_plain_platform_unchanged():
    """纯主平台声明：申请体不变，无伴生。"""
    requests_, companions = parse_users_requirement({"userA": "web", "userB": "windows"})
    assert requests_ == {"userA": "web", "userB": "windows"}
    assert companions == {}


def test_parse_companion_platform():
    """web+windows：只申请 web，伴生映射 userA -> windows。"""
    requests_, companions = parse_users_requirement({"userA": "web+windows"})
    assert requests_ == {"userA": "web"}
    assert companions == {"userA": "windows"}


def test_parse_mixed_users():
    """多用户各自声明：仅声明了伴生的用户有伴生映射。"""
    requests_, companions = parse_users_requirement({"userA": "web+windows", "userB": "web"})
    assert requests_ == {"userA": "web", "userB": "web"}
    assert companions == {"userA": "windows"}


def test_parse_rejects_api_main_platform():
    """主平台不能是 api。"""
    with pytest.raises(ValueError, match="主平台不能是 api"):
        parse_users_requirement({"userA": "api+windows"})


def test_parse_rejects_api_companion():
    """伴生平台不能是 api。"""
    with pytest.raises(ValueError, match="伴生平台不能是 api"):
        parse_users_requirement({"userA": "web+api"})


def test_parse_rejects_triple_platform():
    """不支持多伴生。"""
    with pytest.raises(ValueError, match="只支持"):
        parse_users_requirement({"userA": "web+windows+mac"})


def test_parse_rejects_conflicting_explicit_key():
    """显式声明的伴生键与伴生映射冲突时报错。"""
    with pytest.raises(ValueError, match="冲突"):
        parse_users_requirement({"userA": "web+windows", "userA_windows": "windows"})


def test_validate_companion_platforms_accepts_windows():
    """windows 有对应 AW 目录，校验通过。"""
    validate_companion_platforms({"userA": "windows"})  # 不抛异常


def test_validate_companion_platforms_rejects_unknown():
    """不存在的平台没有 AW 目录，报错。"""
    with pytest.raises(ValueError, match="AW 目录"):
        validate_companion_platforms({"userA": "no_such_platform"})


def _make_windows_user() -> User:
    return User(user_id="userA_windows", platform="windows", ip="127.0.0.1", port=8080)


def test_deferred_setup_runs_once_on_first_aw_fetch():
    """首次取 AW 方法触发一次，之后不再触发。"""
    user = _make_windows_user()
    calls = []
    user.set_deferred_setup(lambda: calls.append(1))

    method = user.should_toast_exists  # 仅取方法，不调用
    assert callable(method)
    assert calls == [1]
    assert user._used is True

    _ = user.should_toast_exists  # 再次取不再触发
    assert calls == [1]


def test_deferred_setup_not_triggered_without_registration():
    """未注册回调时取 AW 方法不报错、行为不变。"""
    user = _make_windows_user()
    assert callable(user.should_toast_exists)


def test_deferred_setup_not_triggered_by_non_callable():
    """extra 字段访问不触发懒执行。"""
    user = _make_windows_user()
    calls = []
    user.set_deferred_setup(lambda: calls.append(1))
    user.extra["env"] = "test"

    assert user.env == "test"
    assert calls == []


def test_deferred_setup_exception_propagates_and_cleared():
    """懒执行失败：异常从取方法处抛出，且回调已清空不重复执行。"""
    user = _make_windows_user()

    def boom():
        raise RuntimeError("start_app failed")

    user.set_deferred_setup(boom)
    with pytest.raises(RuntimeError, match="start_app failed"):
        _ = user.should_toast_exists

    _ = user.should_toast_exists  # 已清空，不再触发


def _make_user_triple():
    """构造 主用户(web) + 伴生用户(windows) + api 用户 三元组。"""
    main = User(user_id="userA", platform="web", ip="127.0.0.1", port=8080)
    companion = User(user_id="userA_windows", platform="windows", ip="127.0.0.1", port=8080)
    companion._is_companion = True
    api = User(user_id="userA_api", platform="api", ip="127.0.0.1", port=8080)
    return main, companion, api


def test_report_details_filters_unused_api_and_companion():
    """未使用的伴生用户与 api 用户不进报告；使用过的伴生用户正常展示。"""
    main, companion, api = _make_user_triple()
    instances = {"userA": main, "userA_windows": companion, "userA_api": api}

    details = _build_report_user_details(instances)
    assert set(details) == {"userA"}

    companion._used = True
    details = _build_report_user_details(instances)
    assert set(details) == {"userA", "userA_windows"}
    assert details["userA_windows"]["platform"] == "windows"
    assert details["userA_windows"]["is_api"] is False


def test_keepalive_resources_only_include_applied_machines():
    """keepalive 只包含平台实际返回的机器（伴生/api 用户天然不在其中）。"""
    main, companion, api = _make_user_triple()
    raw = {"userA": {"id": "machine-1", "ip": "1.1.1.1"}}

    result = _build_keepalive_resources(
        {"userA": main, "userA_windows": companion, "userA_api": api}, raw
    )
    assert result == {"userA": {"id": "machine-1", "ip": "1.1.1.1"}}
