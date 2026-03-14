"""
断言函数。

提供测试用例常用的断言方法。
"""

from typing import Any, Dict, List, Optional


def assert_response_ok(response: Dict[str, Any]) -> None:
    """断言响应成功。

    Args:
        response: testagent 返回的响应数据。

    Raises:
        AssertionError: 响应状态不为成功时抛出。
    """
    success = response.get("success", False)
    assert success, f"操作失败: {response.get('message', '未知错误')}"


def assert_json_contains(
    actual: Dict[str, Any],
    expected: Dict[str, Any],
) -> None:
    """断言 JSON 包含期望的字段。

    Args:
        actual: 实际的 JSON 数据。
        expected: 期望包含的字段。

    Raises:
        AssertionError: 字段不匹配时抛出。
    """
    for key, value in expected.items():
        assert key in actual, f"缺少字段: {key}"
        assert actual[key] == value, f"字段 {key} 不匹配: 期望 {value}, 实际 {actual[key]}"


def assert_text_equals(actual: str, expected: str) -> None:
    """断言文本相等。

    Args:
        actual: 实际文本。
        expected: 期望文本。

    Raises:
        AssertionError: 文本不匹配时抛出。
    """
    assert actual == expected, f"文本不匹配: 期望 '{expected}', 实际 '{actual}'"


def assert_text_contains(text: str, substring: str) -> None:
    """断言文本包含子串。

    Args:
        text: 原文本。
        substring: 期望包含的子串。

    Raises:
        AssertionError: 不包含时抛出。
    """
    assert substring in text, f"文本 '{text}' 不包含 '{substring}'"


def assert_in_list(item: Any, items: List[Any]) -> None:
    """断言元素在列表中。

    Args:
        item: 待检查的元素。
        items: 列表。

    Raises:
        AssertionError: 元素不在列表中时抛出。
    """
    assert item in items, f"元素 '{item}' 不在列表 {items} 中"


def assert_not_empty(value: Any) -> None:
    """断言值非空。

    Args:
        value: 待检查的值。

    Raises:
        AssertionError: 值为空时抛出。
    """
    assert value, f"值不应为空: {value}"


def assert_count_equals(items: List[Any], expected: int) -> None:
    """断言列表长度。

    Args:
        items: 列表。
        expected: 期望长度。

    Raises:
        AssertionError: 长度不匹配时抛出。
    """
    actual = len(items)
    assert actual == expected, f"列表长度不匹配: 期望 {expected}, 实际 {actual}"