"""伴生平台（web+windows）解析与懒 hooks 测试。"""

import pytest

from common.users_marker import parse_users_requirement, validate_companion_platforms


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
