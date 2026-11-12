"""模板缺失富诊断测试。"""

from pathlib import Path

import pytest

from common.utils import find_similar_templates


def _make_images(root: Path):
    (root / "images" / "web").mkdir(parents=True)
    (root / "images" / "web" / "摄像头_关闭.png").write_bytes(b"png")
    (root / "images" / "web" / "摄像头_开启_新.png").write_bytes(b"png")
    (root / "images" / "web" / "会中_挂断.png").write_bytes(b"png")


def test_find_similar_templates_ranks_by_name(tmp_path):
    _make_images(tmp_path)
    matches = find_similar_templates("images/web/摄像头_开启.png", tmp_path)
    assert matches, "应至少找到相近文件"
    assert any("摄像头" in m for m in matches)
    assert any("相似" in m for m in matches)


def test_find_similar_templates_empty_root(tmp_path):
    assert find_similar_templates("images/web/x.png", tmp_path) == []


def test_find_similar_templates_max_three(tmp_path):
    _make_images(tmp_path)
    for i in range(6):
        (tmp_path / "images" / "web" / f"摄像头_开启_{i}.png").write_bytes(b"png")
    matches = find_similar_templates("images/web/摄像头_开启.png", tmp_path / "images")
    assert len(matches) <= 3


def test_load_template_or_raise_message(tmp_path, monkeypatch):
    """文件缺失时抛出带绝对路径与相近文件提示的 FileNotFoundError。"""
    from types import SimpleNamespace

    from aw.base_aw import BaseAW

    def _user():
        return SimpleNamespace(
            user_id="userA", platform="windows", account="a", password="p",
            name="测试用户", ip="127.0.0.1", _get_ui_platform=lambda: "windows",
        )

    _make_images(tmp_path)
    import common.utils as utils
    # 注意：helper 内部必须经 utils.get_project_root() 取根目录，monkeypatch 才生效
    monkeypatch.setattr(utils, "get_project_root", lambda: tmp_path)

    class T(BaseAW):
        PLATFORM = "windows"

    aw = T(None, _user())
    with pytest.raises(FileNotFoundError) as ei:
        aw._load_template_or_raise("images/web/摄像头_开启.png")
    msg = str(ei.value)
    assert msg.startswith("图片文件不存在: images/web/摄像头_开启.png")
    assert f"绝对路径: {tmp_path / 'images/web/摄像头_开启.png'}" in msg
    assert "相近文件" in msg


def test_load_template_or_raise_returns_base64(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from aw.base_aw import BaseAW

    def _user():
        return SimpleNamespace(
            user_id="userA", platform="windows", account="a", password="p",
            name="测试用户", ip="127.0.0.1", _get_ui_platform=lambda: "windows",
        )

    _make_images(tmp_path)
    import common.utils as utils
    monkeypatch.setattr(utils, "get_project_root", lambda: tmp_path)

    class T(BaseAW):
        PLATFORM = "windows"

    aw = T(None, _user())
    assert aw._load_template_or_raise("images/web/会中_挂断.png") == "cG5n"
