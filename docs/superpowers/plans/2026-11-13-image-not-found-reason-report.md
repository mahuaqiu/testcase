# 图片找不到失败原因呈现 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "图片找不到"失败时，报告显示失败类型徽章（相似度不足/文本未找到/文件缺失等）+ 关键数值（阈值 vs 实际相似度）+ OCR 实际识别内容，并补齐 worker/ocr_service 日志。

**Architecture:** ocr_service 在未命中响应中返回 `not_found_reason`/`best_confidence`（已算出但没返回）→ worker 沿现有线程本地模式（对标 `_last_response`）透传，动作层用 `format_find_failure` 拼装中文文案，`ActionResult/TaskResult` 增加可选 `error_type` → testcase 报告按 `error_type` 渲染彩色徽章/占位块，本地模板缺失统一为富信息 FileNotFoundError。设计文档：`docs/superpowers/specs/2026-11-12-image-not-found-reason-report-design.md`；视觉验收样张（已获用户批准）：会话可视化目录 `report-image-fail-mockup.html`。

**Tech Stack:** FastAPI + Pydantic（ocr_service）、httpx + dataclasses（autotest worker）、pytest + 自研 HTMLReportGenerator（testcase）。

## Global Constraints

- **全部增量**：不删除/不改名任何既有字段；`error` 平文本字段保留（内容更丰富）。所有新 JSON 字段可选，旧版本混布不破坏。
- **不做错误码枚举**（用户决策）：失败类型是 8 个中文展示词，固定词汇表：`文件缺失 / OCR服务错误 / OCR请求失败 / 文本未找到 / 相似度不足 / 颜色校验未通过 / 距离超限 / 其他`。词汇表以 `worker/actions/failure.py` 与 `common/report_generator.py` 中的映射为准，不得新增词。
- 服务端 `not_found_reason` 枚举固定：`below_threshold / color_check_failed / no_text_recognized / text_not_found / template_not_matched / distance_exceeded`。
- 报告为固定浅色主题（`report_generator.py:_CSS` 硬编码），只允许**追加** CSS 类，不改既有类。
- 仓库与实施顺序：`D:\code\ocr_service`（Task 1-4）→ `D:\code\autotest`（Task 5-7）→ `D:\code\testcase`（Task 8-10）。每个 Task 独立可提交；只做前两阶段时报告自动回退平文本。
- 三个仓库各自独立 git 仓库，**在各自仓库内提交**；testcase 仓库当前分支 `main`（用户已将设计文档并入 main）。
- 测试命令（Git Bash on Windows）：各仓库用自带 venv：`venv/Scripts/python -m pytest <file> -v`。testcase 仓库直接 `python -m pytest tests/unit/... -v`（若 venv 激活失败，回退 `python -m pytest`）。

---

## Phase 1: ocr_service（D:\code\ocr_service）

### Task 1: decode_image 细分失败原因 + data-URI 前缀支持

**Files:**
- Modify: `D:\code\ocr_service\ocr_service\utils\image_utils.py:1-32`
- Test: `D:\code\ocr_service\tests\test_image_utils_decode.py`（新建）

**Interfaces:**
- Consumes: 无（独立工具函数）
- Produces: `decode_image(image_data: bytes | str) -> np.ndarray`，签名不变；空图抛 `ValueError("图片数据为空")`；非法 base64 抛 `ValueError("Base64 解码失败（输入 N 字符）...")`；无法解码抛 `ValueError("图片解码失败（N 字节，格式不支持或数据损坏）")`；字符串输入支持 `data:image/...;base64,` 前缀。

- [ ] **Step 1: 写失败测试**

创建 `D:\code\ocr_service\tests\test_image_utils_decode.py`：

```python
"""decode_image 失败原因细分测试。"""

import base64
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_service.utils.image_utils import decode_image


def _tiny_png_b64() -> str:
    img = np.ones((8, 8, 3), dtype=np.uint8) * 255
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def test_empty_string_raises_empty_error():
    with pytest.raises(ValueError, match="图片数据为空"):
        decode_image("")


def test_data_uri_prefix_is_stripped():
    """yaml 声明支持 data:image/...;base64, 前缀，必须能解码。"""
    prefixed = "data:image/png;base64," + _tiny_png_b64()
    image = decode_image(prefixed)
    assert image.shape[:2] == (8, 8)


def test_invalid_base64_message_contains_length():
    with pytest.raises(ValueError, match="Base64 解码失败"):
        decode_image("!!!not-base64!!!")


def test_corrupt_bytes_message_contains_length():
    with pytest.raises(ValueError, match="图片解码失败"):
        decode_image(b"\x00\x01\x02garbage-not-an-image")


def test_valid_bytes_still_works():
    image = decode_image(base64.b64decode(_tiny_png_b64()))
    assert image.shape[:2] == (8, 8)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/test_image_utils_decode.py -v`
Expected: FAIL（`data:image` 前缀用例解码出乱码、错误消息不匹配）

- [ ] **Step 3: 实现**

修改 `D:\code\ocr_service\ocr_service\utils\image_utils.py`，文件头 import 区（第 5-9 行）加入 `import binascii`，并替换 `decode_image`（第 12-32 行）为：

```python
def decode_image(image_data: bytes | str) -> np.ndarray:
    """解码图像数据为 OpenCV 格式。

    Args:
        image_data: 图像字节数据或 Base64 编码字符串。
            字符串支持 "data:image/...;base64," 前缀（ocr_api.yaml 已声明）。

    Returns:
        np.ndarray: OpenCV 图像数组 (BGR 格式)。

    Raises:
        ValueError: 区分三种失败——空数据 / Base64 非法 / 无法解码（格式不支持或损坏），
            消息中带输入长度，方便下游定位。
    """
    if isinstance(image_data, str):
        # 兼容 data URI 前缀
        if image_data.startswith("data:image"):
            _, _, image_data = image_data.partition(",")
        if not image_data:
            raise ValueError("图片数据为空")
        input_chars = len(image_data)
        try:
            image_data = base64.b64decode(image_data, validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError(f"Base64 解码失败（输入 {input_chars} 字符）: {e}") from e

    if not image_data:
        raise ValueError("图片数据为空")

    # 转换为 numpy 数组
    np_array = np.frombuffer(image_data, np.uint8)
    image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(f"图片解码失败（{len(image_data)} 字节，格式不支持或数据损坏）")

    return image
```

- [ ] **Step 4: 运行确认通过**

Run: `cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/test_image_utils_decode.py tests/test_image_utils_resize.py -v`
Expected: 全部 PASS（resize 测试是既有回归）

- [ ] **Step 5: 提交**

```bash
cd D:/code/ocr_service && git add ocr_service/utils/image_utils.py tests/test_image_utils_decode.py && git commit -m "feat(ocr): decode_image 细分失败原因并支持 data-URI 前缀"
```

### Task 2: ImageMatcher 未命中时返回 not_found_reason / best_confidence

**Files:**
- Modify: `D:\code\ocr_service\ocr_service\models\match_result.py:54-71`
- Modify: `D:\code\ocr_service\ocr_service\core\image_matcher.py`（match_template :152-221、match_all :243-330、match_feature :351-458）
- Test: `D:\code\ocr_service\tests\test_match_diagnostics.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `decode_image`
- Produces: `ImageMatchResult` 新增字段 `not_found_reason: Optional[str]`、`best_confidence: Optional[float]`（未命中时填充，命中/出错时为 None）；`to_dict()` 在非 None 时输出这两键。`not_found_reason ∈ below_threshold / color_check_failed / template_not_matched`（text 类原因由 Task 3 在路由层填充）。

- [ ] **Step 1: 写失败测试**

创建 `D:\code\ocr_service\tests\test_match_diagnostics.py`（测试图片构造方式沿用 tests/test_image_matcher_color.py 的 `_make_panel`）：

```python
"""图像匹配未命中诊断字段测试（not_found_reason / best_confidence）。"""

import base64
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_service.config import ServiceConfig
from ocr_service.core.image_matcher import ImageMatcher


def _encode_bgr(image: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", image)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def _make_panel(with_red_line: bool) -> np.ndarray:
    img = np.ones((60, 140, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (5, 5), (134, 54), (180, 180, 180), 1)
    line_color = (0, 0, 255) if with_red_line else (0, 0, 0)
    cv2.line(img, (15, 25), (120, 25), line_color, 2)
    cv2.putText(img, "ABC", (20, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
    return img


@pytest.fixture
def matcher() -> ImageMatcher:
    config = ServiceConfig(default_match_threshold=0.8, default_match_method="template")
    return ImageMatcher(config=config)


def test_gray_below_threshold_reports_reason_and_best(matcher: ImageMatcher):
    """内容完全不同的模板：below_threshold + best_confidence。"""
    template = _make_panel(with_red_line=True)
    # 大图只有随机噪点，与模板无结构相似性（固定种子，避免偶发高相似）
    rng = np.random.default_rng(42)
    source = rng.integers(0, 255, (220, 320, 3), dtype=np.uint8)

    result = matcher.match_template(
        source_data=_encode_bgr(source),
        template_data=_encode_bgr(template),
        threshold=0.99,
    )

    assert result.status == "success"
    assert result.matches == []
    assert result.not_found_reason == "below_threshold"
    assert result.best_confidence is not None
    assert result.best_confidence < 0.99


def test_color_fail_reports_color_check_failed(matcher: ImageMatcher):
    """灰度过、颜色关不过：color_check_failed，best 为灰度分。"""
    template = _make_panel(with_red_line=True)
    source = np.ones((220, 320, 3), dtype=np.uint8) * 245
    source[80:140, 90:230] = _make_panel(with_red_line=False)

    result = matcher.match_template(
        source_data=_encode_bgr(source),
        template_data=_encode_bgr(template),
        threshold=0.8,
    )

    assert result.status == "success"
    assert result.matches == []
    assert result.not_found_reason == "color_check_failed"
    assert result.best_confidence is not None
    assert result.best_confidence >= 0.8


def test_template_larger_than_source_reports_reason(matcher: ImageMatcher):
    template = _make_panel(with_red_line=True)
    source = np.ones((40, 80, 3), dtype=np.uint8) * 245  # 比模板(60x140)小

    result = matcher.match_template(
        source_data=_encode_bgr(source),
        template_data=_encode_bgr(template),
        threshold=0.8,
    )

    assert result.status == "success"
    assert result.matches == []
    assert result.not_found_reason == "template_not_matched"


def test_match_success_has_no_diagnostic_fields(matcher: ImageMatcher):
    """命中时不携带诊断字段。"""
    template = _make_panel(with_red_line=True)
    source = np.ones((220, 320, 3), dtype=np.uint8) * 245
    source[80:140, 90:230] = _make_panel(with_red_line=True)

    result = matcher.match_template(
        source_data=_encode_bgr(source),
        template_data=_encode_bgr(template),
        threshold=0.8,
    )

    assert len(result.matches) == 1
    assert result.not_found_reason is None
    assert result.best_confidence is None


def test_match_all_gray_fail_reports_below_threshold(matcher: ImageMatcher):
    """多目标路径：全图无灰度候选时 below_threshold。"""
    template = _make_panel(with_red_line=True)
    rng = np.random.default_rng(42)
    source = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)

    result = matcher.match_all(
        source_data=_encode_bgr(source),
        template_data=_encode_bgr(template),
        threshold=0.99,
    )

    assert result.status == "success"
    assert result.matches == []
    assert result.not_found_reason == "below_threshold"
    assert result.best_confidence is not None


def test_to_dict_includes_diagnostics(matcher: ImageMatcher):
    template = _make_panel(with_red_line=True)
    source = np.ones((220, 320, 3), dtype=np.uint8) * 245
    source[80:140, 90:230] = _make_panel(with_red_line=False)

    result = matcher.match_template(
        source_data=_encode_bgr(source),
        template_data=_encode_bgr(template),
        threshold=0.8,
    )

    d = result.to_dict()
    assert d["not_found_reason"] == "color_check_failed"
    assert "best_confidence" in d
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/test_match_diagnostics.py -v`
Expected: FAIL（`ImageMatchResult` 无 `not_found_reason` 属性）

- [ ] **Step 3: 扩展 ImageMatchResult**

修改 `D:\code\ocr_service\ocr_service\models\match_result.py`，`ImageMatchResult`（第 54-71 行）替换为：

```python
@dataclass
class ImageMatchResult:
    """图像匹配完整结果。"""

    status: str
    matches: list[MatchResult] = field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None
    # 未命中诊断：status="success" 且 matches 为空时填充，方便下游定位"为什么没匹配上"
    not_found_reason: Optional[str] = None
    best_confidence: Optional[float] = None

    def to_dict(self) -> dict:
        result = {
            "status": self.status,
            "matches": [m.to_dict() for m in self.matches],
            "duration_ms": self.duration_ms,
        }
        if self.error:
            result["error"] = self.error
        if self.not_found_reason is not None:
            result["not_found_reason"] = self.not_found_reason
        if self.best_confidence is not None:
            result["best_confidence"] = self.best_confidence
        return result
```

- [ ] **Step 4: match_template 填充诊断字段**

修改 `D:\code\ocr_service\ocr_service\core\image_matcher.py` `match_template`：

4a. 模板大于源图分支（:170-174）改为：

```python
                return ImageMatchResult(
                    status="success",
                    matches=[],
                    duration_ms=int((time.time() - start_time) * 1000),
                    not_found_reason="template_not_matched",
                )
```

4b. 灰度未过/颜色关不过的分支（:183-201 附近）：删除原 `matches = []` 后的 if/else 中 `else` 分支的独立日志保留，改为在 `duration_ms = ...` 之后、`return ImageMatchResult(...)`（:212-214）之前插入未命中收尾，并将返回改为：

```python
            duration_ms = int((time.time() - start_time) * 1000)
            if not matches:
                reason = "below_threshold" if gray_score < threshold else "color_check_failed"
                logger.info(
                    f"[MATCH] done hits=0 reason={reason} "
                    f"best={gray_score:.4f} thr={threshold} duration_ms={duration_ms}"
                )
                return ImageMatchResult(
                    status="success",
                    matches=[],
                    duration_ms=duration_ms,
                    not_found_reason=reason,
                    best_confidence=round(gray_score, 4),
                )
            logger.info(
                f"[MATCH] done hits={len(matches)} duration_ms={duration_ms}"
                + (
                    f" | hit gray={matches[0].confidence:.4f} bbox=({matches[0].bbox.x},{matches[0].bbox.y},{matches[0].bbox.width},{matches[0].bbox.height})"
                    if matches
                    else ""
                )
            )
            return ImageMatchResult(
                status="success", matches=matches, duration_ms=duration_ms
            )
```

（原 :199-201 的 `gray fail` 过程日志保留不动。）

- [ ] **Step 5: match_all 填充诊断字段**

修改 `match_all` 同样两处：

5a. 模板大于源图分支（:260-264）加 `not_found_reason="template_not_matched"`（同 4a 写法）。

5b. 收尾（:317-323）改为：

```python
            duration_ms = int((time.time() - start_time) * 1000)
            if not matches:
                best = float(np.max(result)) if result.size else 0.0
                reason = "color_check_failed" if rectangles else "below_threshold"
                logger.info(
                    f"[MATCH] done hits=0 reason={reason} "
                    f"best={best:.4f} thr={threshold} duration_ms={duration_ms}"
                )
                return ImageMatchResult(
                    status="success",
                    matches=[],
                    duration_ms=duration_ms,
                    not_found_reason=reason,
                    best_confidence=round(best, 4),
                )
            logger.info(f"[MATCH] done hits={len(matches)} duration_ms={duration_ms}")
            return ImageMatchResult(
                status="success", matches=matches, duration_ms=duration_ms
            )
```

- [ ] **Step 6: match_feature 填充诊断字段**

`match_feature` 两处未命中返回（:370-376 描述子为空、:445-449 最终返回）统一改为在 `matches` 为空时填 `not_found_reason="below_threshold"`（`best_confidence` 仅在算出 `confidence` 后才有值，描述子为空时保持 None）：

6a. :370-376 改为：

```python
            if des1 is None or des2 is None:
                duration_ms = int((time.time() - start_time) * 1000)
                return ImageMatchResult(
                    status="success",
                    matches=[],
                    duration_ms=duration_ms,
                    not_found_reason="below_threshold",
                )
```

6b. :392 `result_matches = []` 之前初始化 `confidence = None`，:443-449 的最终返回改为：

```python
            duration_ms = int((time.time() - start_time) * 1000)
            if not result_matches:
                return ImageMatchResult(
                    status="success",
                    matches=[],
                    duration_ms=duration_ms,
                    not_found_reason="below_threshold",
                    best_confidence=round(confidence, 4) if confidence is not None else None,
                )
            return ImageMatchResult(
                status="success",
                matches=result_matches,
                duration_ms=duration_ms,
            )
```

（注意：`confidence` 仅在单应性分支内被赋值，必须先初始化为 None，否则 `M is None` 路径会 NameError。）

- [ ] **Step 7: 运行确认通过**

Run: `cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/test_match_diagnostics.py tests/test_image_matcher_color.py -v`
Expected: 全部 PASS（颜色测试是既有回归）

- [ ] **Step 8: 提交**

```bash
cd D:/code/ocr_service && git add ocr_service/models/match_result.py ocr_service/core/image_matcher.py tests/test_match_diagnostics.py && git commit -m "feat(match): 未命中时返回 not_found_reason 与 best_confidence"
```

### Task 3: 路由层透传 + schema 增量字段 + 修吞错误 bug

**Files:**
- Modify: `D:\code\ocr_service\ocr_service\api\schemas.py`（OCRResponse :100-108、OCRTextResponse :130-137、ImageMatchResponse :156-163、TextNearImageResponse :181-191）
- Modify: `D:\code\ocr_service\ocr_service\api\routes.py`（get_coord_by_text :206-262、image_match :338-359、match_near_text :428-481）
- Test: `D:\code\ocr_service\tests\test_routes_not_found.py`（新建）

**Interfaces:**
- Consumes: Task 2 的 `ImageMatchResult.not_found_reason/best_confidence`
- Produces: HTTP 响应新增可选字段 `not_found_reason`/`best_confidence`/`nearest_distance`；`GET /ocr/get_coord_by_text` 引擎错误时返回 `status="error"` + `error` 字段（原来被吞成 success+空）。这三种字段是 worker 侧（Task 5/6）读取的契约。

- [ ] **Step 1: schema 增量字段**

修改 `D:\code\ocr_service\ocr_service\api\schemas.py`。文件头 import（第 6 行）确认已有 `Optional`。给 4 个响应模型各追加同样 3 个字段（放在各自 `error` 字段之后）：

OCRResponse（:108 `error` 行后）：

```python
    not_found_reason: Optional[str] = Field(
        default=None,
        description="未找到原因: below_threshold/color_check_failed/no_text_recognized/text_not_found/template_not_matched/distance_exceeded",
    )
    best_confidence: Optional[float] = Field(default=None, description="未命中时的最高相似度/特征分")
    nearest_distance: Optional[float] = Field(default=None, description="match_near_text：最近候选距离（像素）")
```

OCRTextResponse、ImageMatchResponse、TextNearImageResponse 的 `error` 行后追加**完全相同的 3 行字段**（`nearest_distance` 在非 near_text 模型中恒为 None，仅为统一信封）。

- [ ] **Step 2: 写失败测试**

创建 `D:\code\ocr_service\tests\test_routes_not_found.py`：

```python
"""路由层未命中诊断与吞错误修复测试。"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_service.api.routes import image_match, image_match_near_text, ocr_get_coord_by_text
from ocr_service.api.schemas import (
    ImageMatchRequest,
    OCRRequest,
    PointModel,
    TextBlockModel,
    TextNearImageRequest,
)


def _engine_result(status="success", texts=None, error=None):
    return SimpleNamespace(status=status, texts=texts or [], duration_ms=12, error=error)


def _text_block(text, x, y):
    return TextBlockModel(
        text=text,
        confidence=0.98,
        bbox=[[x, y], [x + 10, y], [x + 10, y + 10], [x, y + 10]],
        center=PointModel(x=x, y=y),
    )


def test_coord_by_text_engine_error_returns_error_status():
    """引擎报错必须透传 status=error，不得吞成 success+空。"""
    with patch("ocr_service.api.routes.get_ocr_engine") as g:
        g.return_value.recognize.return_value = _engine_result(status="error", error="模型加载失败")
        req = OCRRequest(image="aaa", filter_text="密码")
        resp = asyncio.run(ocr_get_coord_by_text(req))

    assert resp.status == "error"
    assert resp.error == "模型加载失败"


def test_coord_by_text_no_text_recognized():
    with patch("ocr_service.api.routes.get_ocr_engine") as g:
        g.return_value.recognize.return_value = _engine_result(status="success", texts=[])
        req = OCRRequest(image="aaa", filter_text="密码")
        resp = asyncio.run(ocr_get_coord_by_text(req))

    assert resp.status == "success"
    assert resp.texts == []
    assert resp.not_found_reason == "no_text_recognized"


def test_coord_by_text_text_not_found():
    with patch("ocr_service.api.routes.get_ocr_engine") as g:
        g.return_value.recognize.return_value = _engine_result(
            status="success", texts=[_text_block("用户名", 100, 200)]
        )
        req = OCRRequest(image="aaa", filter_text="密码")
        resp = asyncio.run(ocr_get_coord_by_text(req))

    assert resp.status == "success"
    assert resp.not_found_reason == "text_not_found"
    assert len(resp.ocr_info) == 1  # 屏幕实际识别内容仍返回


def test_image_match_passthrough_diagnostics():
    matcher_result = SimpleNamespace(
        status="success", matches=[], duration_ms=9,
        not_found_reason="below_threshold", best_confidence=0.7231, error=None,
    )
    with patch("ocr_service.api.routes.get_image_matcher") as g:
        g.return_value.match.return_value = matcher_result
        req = ImageMatchRequest(source_image="aaa", template_image="bbb", confidence_threshold=0.9)
        resp = asyncio.run(image_match(req))

    assert resp.status == "success"
    assert resp.not_found_reason == "below_threshold"
    assert resp.best_confidence == 0.7231


def test_near_text_distance_exceeded_reports_nearest():
    """文字找到、模板也匹配到，但全部超出 max_distance：distance_exceeded + 最近距离。"""
    engine_result = _engine_result(status="success", texts=[_text_block("设置", 100, 100)])
    matched = SimpleNamespace(
        confidence=0.95,
        bbox=SimpleNamespace(x=0, y=0, width=20, height=20),
        center=SimpleNamespace(x=10, y=10),
    )
    matcher_result = SimpleNamespace(
        status="success", matches=[matched], duration_ms=9,
        not_found_reason=None, best_confidence=None, error=None,
    )
    with patch("ocr_service.api.routes.get_ocr_engine") as ge, \
         patch("ocr_service.api.routes.get_image_matcher") as gm:
        ge.return_value.recognize.return_value = engine_result
        gm.return_value.match.return_value = matcher_result
        req = TextNearImageRequest(
            image="aaa", target_image="bbb", filter_text="设置", max_distance=5,
        )
        resp = asyncio.run(image_match_near_text(req))

    assert resp.status == "success"
    assert resp.not_found_reason == "distance_exceeded"
    assert resp.nearest_distance is not None and resp.nearest_distance > 5
```

- [ ] **Step 3: 运行确认失败**

Run: `cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/test_routes_not_found.py -v`
Expected: FAIL（engine error 用例得到 success；`not_found_reason`/`nearest_distance` 属性不存在或为 None）

- [ ] **Step 4: 路由实现**

4a. `D:\code\ocr_service\ocr_service\api\routes.py` `ocr_get_coord_by_text`：把 :206-213 的吞错误分支替换为：

```python
    if result.status != "success":
        logger.error(f"[OCR] engine error: {result.error}")
        return OCRResponse(
            status="error",
            texts=[],
            coords=[],
            ocr_info=all_ocr_info,
            duration_ms=result.duration_ms,
            error=result.error,
        )

    if not result.texts:
        logger.info(f"[OCR] no text recognized: filter_text=\"{request.filter_text}\" recognized=0")
        return OCRResponse(
            status="success",
            texts=[],
            coords=[],
            ocr_info=all_ocr_info,
            duration_ms=result.duration_ms,
            not_found_reason="no_text_recognized",
        )
```

4b. 同函数 :236-243 的"过滤后无命中"分支改为：

```python
    if not text_blocks:
        logger.info(
            f"[OCR] text not found: filter_text=\"{request.filter_text}\" "
            f"recognized={len(all_ocr_info)}"
        )
        return OCRResponse(
            status="success",
            texts=[],
            coords=[],
            ocr_info=all_ocr_info,
            duration_ms=duration_ms,
            not_found_reason="text_not_found",
        )
```

4c. `image_match`（:338-359）返回体追加两行（`error=result.error,` 之后）：

```python
        not_found_reason=result.not_found_reason,
        best_confidence=result.best_confidence,
```

4d. `image_match_near_text` 三处未命中返回体追加字段：

- :428-437（文字未找到）追加 `not_found_reason="text_not_found",`
- :451-460（模板无匹配）追加 `not_found_reason="template_not_matched", best_confidence=match_result.best_confidence,`
- :472-481（距离超限）改为：

```python
    if not valid_matches:
        nearest = min(calc_distance(m) for m in match_result.matches)
        return TextNearImageResponse(
            status="success",
            text_position=PointModel(x=text_center.x, y=text_center.y),
            match=None,
            coords=[],
            ocr_info=all_ocr_info,
            distance=None,
            not_found_reason="distance_exceeded",
            nearest_distance=float(nearest),
            duration_ms=int((time.time() - start_time) * 1000),
        )
```

（`logger` 已在 routes.py 顶部 import；`math` 同理，`calc_distance` 使用 `math.sqrt`，该函数定义在 :463-464 不变。）

- [ ] **Step 5: 运行确认通过**

Run: `cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/test_routes_not_found.py tests/test_match_diagnostics.py tests/test_image_matcher_color.py -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
cd D:/code/ocr_service && git add ocr_service/api/schemas.py ocr_service/api/routes.py tests/test_routes_not_found.py && git commit -m "feat(api): 未命中响应透传诊断字段，修复 get_coord_by_text 吞引擎错误"
```

### Task 4: ocr_service 日志补齐 + API 文档

**Files:**
- Modify: `D:\code\ocr_service\ocr_service\server.py:106-125`（format_response_log）
- Modify: `D:\code\ocr_service\ocr_api.yaml`（响应 schema 文档）
- Test: `D:\code\ocr_service\tests\test_response_log_format.py`（新建）

**Interfaces:**
- Consumes: Task 3 的响应字段
- Produces: `[RESPONSE]` 日志行包含 `ocr_info: [N items]`、`not_found_reason`、`best_confidence`、`nearest_distance`。

- [ ] **Step 1: 写失败测试**

创建 `D:\code\ocr_service\tests\test_response_log_format.py`：

```python
"""[RESPONSE] 日志字段覆盖测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_service.server import format_response_log


def test_response_log_includes_diagnostics_and_ocr_info():
    body = {
        "status": "success",
        "texts": [],
        "coords": [],
        "matches": [],
        "ocr_info": [{"text": "a", "center": {"x": 1, "y": 2}},
                     {"text": "b", "center": {"x": 3, "y": 4}}],
        "not_found_reason": "below_threshold",
        "best_confidence": 0.7231,
        "nearest_distance": None,
        "duration_ms": 9,
        "error": None,
    }
    out = format_response_log(type("R", (), {"method": "POST", "url": type("U", (), {"path": "/image/match"})()})(), body, 200)

    assert "ocr_info: [2 items]" in out
    assert "not_found_reason: below_threshold" in out
    assert "best_confidence: 0.7231" in out
    assert "nearest_distance" not in out  # None 值不输出
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/test_response_log_format.py -v`
Expected: FAIL（`ocr_info`/`not_found_reason` 不在输出中）

- [ ] **Step 3: 实现**

修改 `D:\code\ocr_service\ocr_service\server.py` `format_response_log`（:106-125），键列表与列表处理改为：

```python
    if isinstance(response_body, dict):
        # 只记录关键字段（ocr_info 记条数，诊断字段原样）
        list_keys = {"texts", "coords", "matches", "ocr_info"}
        for key in ["status", "texts", "coords", "duration_ms", "error", "text", "matches",
                    "ocr_info", "not_found_reason", "best_confidence", "nearest_distance"]:
            if key not in response_body or response_body[key] is None:
                continue
            value = response_body[key]
            if key in list_keys and isinstance(value, list):
                value = f"[{len(value)} items]"
            lines.append(f"  {key}: {value}")
```

- [ ] **Step 4: ocr_api.yaml 补文档**

在 `D:\code\ocr_service\ocr_api.yaml` 中找到 `OCRResponse`、`OCRTextResponse`、`ImageMatchResponse`、`TextNearImageResponse` 四个 schema 的 `error` 属性定义，其后各插入（缩进与相邻属性一致）：

```yaml
        not_found_reason:
          type: string
          nullable: true
          description: 未找到原因 below_threshold/color_check_failed/no_text_recognized/text_not_found/template_not_matched/distance_exceeded（status=success 且结果为空时返回）
        best_confidence:
          type: number
          format: float
          nullable: true
          description: 未命中时的最高相似度/特征分
        nearest_distance:
          type: number
          format: float
          nullable: true
          description: 最近候选距离（像素），仅 match_near_text 距离超限时返回
```

同时在 yaml 中 `image`/`source_image`/`target_image` 的描述里确认"支持 `data:image/...;base64,` 前缀"的表述（本计划 Task 1 已使其成真，无需改文字；若 yaml 无此描述则跳过）。

- [ ] **Step 5: 运行确认通过 + 提交**

Run: `cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/ -v`
Expected: 全部 PASS

```bash
cd D:/code/ocr_service && git add ocr_service/server.py ocr_api.yaml tests/test_response_log_format.py && git commit -m "feat(log): [RESPONSE] 日志补充 ocr_info 条数与未命中诊断字段"
```

---

## Phase 2: autotest worker（D:\code\autotest）

### Task 5: OCRClient 记录 last_failure（不再丢失败原因）

**Files:**
- Modify: `D:\code\autotest\common\ocr_client.py`（线程本地属性 :134-150、recognize :152-208、find_text :210-260 附近、match_image :287-354、match_near_text :400-456、_post :471-507、访问器 :519-530）
- Test: `D:\code\autotest\tests\common\test_ocr_client_last_failure.py`（新建）

**Interfaces:**
- Consumes: Task 3 的响应字段（旧服务没有这些字段时取到 None，自动降级）
- Produces: `OCRClient.get_last_failure() -> dict | None`，失败/未命中时返回 `{"status", "error", "http_status", "not_found_reason", "best_confidence", "nearest_distance"}`，成功时为 None；线程隔离（与 `_last_response` 同机制）。Task 6 的 `_get_last_failure` 依赖它。

- [ ] **Step 1: 写失败测试**

创建 `D:\code\autotest\tests\common\test_ocr_client_last_failure.py`：

```python
"""OCRClient.last_failure 线程本地诊断测试。"""

import base64
import io

import httpx
from PIL import Image

from common.ocr_client import OCRClient


def _jpeg_b64() -> str:
    """真实 JPEG 字节，避免 _prepare_ocr_source 重编码分支出错。"""
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 255, 255)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _make_client(handler) -> OCRClient:
    client = OCRClient(base_url="http://test", timeout=5000, retry=0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler), timeout=5, trust_env=False
    )
    return client


def test_service_error_recorded():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "error": "模型加载失败"})

    client = _make_client(handler)
    assert client.recognize(b"fake") == []
    failure = client.get_last_failure()
    assert failure["status"] == "error"
    assert failure["error"] == "模型加载失败"


def test_not_found_reason_recorded():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "success", "matches": [],
            "not_found_reason": "below_threshold", "best_confidence": 0.7231,
        })

    client = _make_client(handler)
    assert client.match_image(b"src", b"tpl", threshold=0.9) == []
    failure = client.get_last_failure()
    assert failure["not_found_reason"] == "below_threshold"
    assert failure["best_confidence"] == 0.7231


def test_http_error_records_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unavailable"})

    client = _make_client(handler)
    assert client.recognize(b"fake") == []
    failure = client.get_last_failure()
    assert failure["status"] == "error"
    assert failure["http_status"] == 503


def test_success_resets_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "success",
            "texts": [{"text": "a", "confidence": 0.9,
                       "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]],
                       "center": {"x": 0, "y": 0}}],
        })

    client = _make_client(handler)
    client.match_image(b"src", b"tpl")  # 先制造一次失败
    client.recognize(base64.b64decode(_jpeg_b64()))
    assert client.get_last_failure() is None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/code/autotest && venv/Scripts/python -m pytest tests/common/test_ocr_client_last_failure.py -v`
Expected: FAIL（`get_last_failure` 属性不存在）

- [ ] **Step 3: 实现**

3a. `D:\code\autotest\common\ocr_client.py` 在 `_last_ocr_results` 属性（:143-150）之后追加：

```python
    @property
    def _last_failure(self) -> dict | None:
        """最后一次调用失败/未命中的诊断（线程隔离）。"""
        return getattr(self._tls, "last_failure", None)

    @_last_failure.setter
    def _last_failure(self, value: dict | None) -> None:
        self._tls.last_failure = value

    def _record_failure(self, response: dict) -> dict:
        """记录一次失败/未命中的诊断信息，供动作层在返回值之外读取原因。"""
        self._last_failure = {
            "status": response.get("status"),
            "error": response.get("error"),
            "http_status": response.get("http_status"),
            "not_found_reason": response.get("not_found_reason"),
            "best_confidence": response.get("best_confidence"),
            "nearest_distance": response.get("nearest_distance"),
        }
        return self._last_failure
```

3b. `recognize`（:152）：函数体第一行（`compressed = ...` 之前）加 `self._last_failure = None`；:183-185 错误分支改为：

```python
        if response.get("status") != "success":
            self._record_failure(response)
            logger.warning(f"OCR识别失败: status={response.get('status')}, error={response.get('error')}")
            return []
```

3c. `find_text`（:210 附近）：函数体第一行加 `self._last_failure = None`；:241-243 错误分支与 :246-248 未找到分支同样处理（未找到分支加 `self._record_failure(response)`，日志行保留）。

3d. `match_image`（:287）：函数体第一行加 `self._last_failure = None`；:330-332 错误分支加 `self._record_failure(response)`；:351-352 的 `else`（matches 为空）分支加 `self._record_failure(response)`。

3e. `match_near_text`（:400 附近）：函数体第一行加 `self._last_failure = None`；:438-440 错误分支与 :443-445 未找到分支加 `self._record_failure(response)`。

3f. `_post` 最终失败（:504-507）改为（日志与缓存体都带上 HTTP 状态码）：

```python
        http_status = None
        response = getattr(last_error, "response", None)
        if response is not None:
            http_status = response.status_code
        logger.error(f"OCR请求最终失败: {url}, http_status={http_status}, 错误: {last_error}")
        error_result = {"status": "error", "error": str(last_error)}
        if http_status is not None:
            error_result["http_status"] = http_status
        self._last_response = error_result  # 缓存错误结果
        self._record_failure(error_result)
        return error_result
```

- [ ] **Step 4: 运行确认通过**

Run: `cd D:/code/autotest && venv/Scripts/python -m pytest tests/common/test_ocr_client_last_failure.py tests/common/test_ocr_client_threadlocal.py -v`
Expected: 全部 PASS（threadlocal 是既有回归）

- [ ] **Step 5: 提交**

```bash
cd D:/code/autotest && git add common/ocr_client.py tests/common/test_ocr_client_last_failure.py && git commit -m "feat(ocr-client): 线程本地记录 last_failure，不再丢失服务端失败原因"
```

### Task 6: 动作层统一失败文案 format_find_failure

**Files:**
- Create: `D:\code\autotest\worker\actions\failure.py`
- Modify: `D:\code\autotest\worker\actions\base.py`（BaseActionExecutor :201-272 追加访问器；find 助手 :304-337、:339-380 换日志）
- Modify: `D:\code\autotest\worker\actions\image.py`、`D:\code\autotest\worker\actions\ocr.py`（固定文案替换，站点见 Step 4）
- Test: `D:\code\autotest\tests\actions\test_failure_format.py`（新建）

**Interfaces:**
- Consumes: Task 5 的 `OCRClient.get_last_failure()`
- Produces:
  - `format_find_failure(failure: dict | None, target: str, threshold: float | None = None, index: int = 0, kind: str = "text") -> tuple[str, str]`，返回 `(error_message, error_type)`；`kind ∈ "text" | "image"`。
  - `BaseActionExecutor._get_last_failure(platform) -> dict | None`
  - `ActionResult.error` 为中文文案、`ActionResult.error_type` 为 8 词词汇表之一（词汇表见 Global Constraints）。

- [ ] **Step 1: 写失败测试**

创建 `D:\code\autotest\tests\actions\test_failure_format.py`：

```python
"""format_find_failure 文案与类型测试。"""

from worker.actions.failure import format_find_failure


def test_below_threshold_message_with_numbers():
    msg, err_type = format_find_failure(
        {"status": "success", "not_found_reason": "below_threshold", "best_confidence": 0.72},
        target="images/web/会中_挂断.png", threshold=0.9, kind="image",
    )
    assert msg == '未找到目标图片"images/web/会中_挂断.png"：最高相似度 0.72，低于阈值 0.90'
    assert err_type == "相似度不足"


def test_color_check_failed():
    msg, err_type = format_find_failure(
        {"status": "success", "not_found_reason": "color_check_failed", "best_confidence": 0.95},
        target="tpl.png", threshold=0.9, kind="image",
    )
    assert "灰度相似度 0.95 达标" in msg and "颜色校验未通过" in msg
    assert err_type == "颜色校验未通过"


def test_text_not_found():
    msg, err_type = format_find_failure(
        {"status": "success", "not_found_reason": "text_not_found"},
        target="密码", kind="text",
    )
    assert msg == '未找到文本 "密码"'
    assert err_type == "文本未找到"


def test_no_text_recognized():
    msg, err_type = format_find_failure(
        {"status": "success", "not_found_reason": "no_text_recognized"},
        target="密码", kind="text",
    )
    assert "屏幕上未识别到任何文字" in msg
    assert err_type == "文本未找到"


def test_distance_exceeded():
    msg, err_type = format_find_failure(
        {"status": "success", "not_found_reason": "distance_exceeded", "nearest_distance": 812.4},
        target="btn.png", kind="image",
    )
    assert "812" in msg and "距离超限" == err_type


def test_service_error():
    msg, err_type = format_find_failure(
        {"status": "error", "error": "模型加载失败"}, target="密码", kind="text",
    )
    assert msg == "OCR 服务错误: 模型加载失败"
    assert err_type == "OCR服务错误"


def test_http_error():
    msg, err_type = format_find_failure(
        {"status": "error", "error": "Connection refused", "http_status": 503},
        target="密码", kind="text",
    )
    assert "HTTP 503" in msg
    assert err_type == "OCR请求失败"


def test_index_suffix():
    msg, _ = format_find_failure(
        {"status": "success", "not_found_reason": "text_not_found"},
        target="密码", index=2, kind="text",
    )
    assert msg.endswith(" at index 2")


def test_none_failure_fallback():
    msg, err_type = format_find_failure(None, target="密码", kind="text")
    assert "密码" in msg
    assert err_type == "其他"


def test_find_image_position_logs_structured_summary(caplog):
    """find 助手失败日志是一行结构化摘要，不再倾倒 ocr_response 整包。"""
    import logging
    from types import SimpleNamespace

    from worker.actions.image import ImageClickAction

    class _StubClient:
        def get_last_failure(self):
            return {"status": "success", "not_found_reason": "below_threshold",
                    "best_confidence": 0.72, "error": None}

        def get_last_ocr_info(self):
            return []

    class _StubPlatform:
        ocr_client = _StubClient()

        def _find_image_position(self, *args, **kwargs):
            return None

    executor = ImageClickAction()
    with caplog.at_level(logging.WARNING):
        assert executor._find_image_position(_StubPlatform(), b"src", b"tpl", 0.9, 0) is None

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "reason=below_threshold" in joined
    assert "best=0.72" in joined
    assert "ocr_response" not in joined
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/code/autotest && venv/Scripts/python -m pytest tests/actions/test_failure_format.py -v`
Expected: FAIL（`worker.actions.failure` 模块不存在）

- [ ] **Step 3: 创建 failure.py**

创建 `D:\code\autotest\worker\actions\failure.py`：

```python
"""find 类动作失败文案的统一构造。

ocr_*/image_* 动作失败时的 error/error_type 全部经过这里，
保证 worker 日志、ActionResult、测试报告三处文案同源。
error_type 词汇表（8 词，报告端按词配色，勿新增）：
文件缺失 / OCR服务错误 / OCR请求失败 / 文本未找到 / 相似度不足 / 颜色校验未通过 / 距离超限 / 其他
"""

from __future__ import annotations


def _index_suffix(index: int) -> str:
    return f" at index {index}" if index > 0 else ""


def format_find_failure(
    failure: dict | None,
    target: str,
    threshold: float | None = None,
    index: int = 0,
    kind: str = "text",
) -> tuple[str, str]:
    """把一次 find 失败的诊断信息转成 (可读消息, 失败类型)。

    Args:
        failure: OCRClient.get_last_failure() 的返回；None 表示拿不到诊断（旧服务/本地失败）。
        target: 目标描述（文本内容或模板图片路径）。
        threshold: 动作传入的匹配阈值（文本类无阈值，传 None）。
        index: 目标序号（>0 时追加到消息末尾）。
        kind: "text" 文本查找 / "image" 图像匹配，决定兜底文案。

    Returns:
        (error_message, error_type)
    """
    suffix = _index_suffix(index)

    # 拿不到诊断：按目标类型给兜底文案
    if not failure:
        if kind == "image":
            return (f'未找到目标图片"{target}"{suffix}', "其他")
        return (f'未找到文本 "{target}"{suffix}', "文本未找到")

    # 传输层 / 服务层错误
    if failure.get("status") == "error":
        if failure.get("http_status") is not None:
            return (
                f"OCR 请求失败: HTTP {failure['http_status']} - {failure.get('error')}{suffix}",
                "OCR请求失败",
            )
        return (f"OCR 服务错误: {failure.get('error')}{suffix}", "OCR服务错误")

    reason = failure.get("not_found_reason")
    best = failure.get("best_confidence")

    if reason == "color_check_failed":
        if best is not None:
            return (
                f'未找到目标图片"{target}"：灰度相似度 {best:.2f} 达标，但颜色校验未通过{suffix}',
                "颜色校验未通过",
            )
        return (f'未找到目标图片"{target}"：颜色校验未通过{suffix}', "颜色校验未通过")

    if reason == "distance_exceeded":
        distance = failure.get("nearest_distance")
        return (
            f'未找到"{target}"附近的图片：最近候选距离 {distance:.0f}px，超过上限{suffix}',
            "距离超限",
        )

    if reason == "no_text_recognized":
        return (f'屏幕上未识别到任何文字，未找到 "{target}"{suffix}', "文本未找到")

    if reason == "text_not_found":
        return (f'未找到文本 "{target}"{suffix}', "文本未找到")

    if reason == "template_not_matched":
        # 模板比源图大 / 文本附近模板未命中
        if kind == "image":
            return (f'未找到目标图片"{target}"（模板与屏幕内容不匹配）{suffix}', "其他")
        return (f'未找到目标图片 "{target}"{suffix}', "相似度不足")

    # 未命中但无细分原因（旧版服务）：有数值时报"差多少"
    if kind == "image":
        if best is not None and threshold is not None:
            return (
                f'未找到目标图片"{target}"：最高相似度 {best:.2f}，低于阈值 {threshold:.2f}{suffix}',
                "相似度不足",
            )
        return (f'未找到目标图片"{target}"{suffix}', "相似度不足")

    return (f'未找到文本 "{target}"{suffix}', "文本未找到")
```

- [ ] **Step 4: BaseActionExecutor 访问器 + find 助手日志改造**

4a. `D:\code\autotest\worker\actions\base.py` 在 `_get_last_ocr_info`（:258-272）之后追加：

```python
    def _get_last_failure(self, platform: "PlatformManager") -> dict | None:
        """
        获取最后一次 OCR/Image 调用的失败诊断。

        Args:
            platform: 平台管理器

        Returns:
            dict | None: 失败/未命中诊断为 None 时返回 None
        """
        if platform.ocr_client and hasattr(platform.ocr_client, "get_last_failure"):
            return platform.ocr_client.get_last_failure()
        return None
```

4b. `_find_image_position`（:304-337）：把 :327-335 的整包 dump 替换为一行结构化摘要（保留返回语义）：

```python
        position = platform._find_image_position(source_bytes, template_base64, threshold, index)

        # 图像匹配失败时打一行可读摘要（与报告文案同源，不再倾倒原始响应）
        if position is None and platform.ocr_client:
            failure = self._get_last_failure(platform) or {}
            logger.warning(
                f"Image match failed: threshold={threshold}, index={index}, "
                f"reason={failure.get('not_found_reason')}, best={failure.get('best_confidence')}, "
                f"error={failure.get('error')}"
            )

        return position
```

4c. `_find_text_with_fallback`（:339-380）：把 :370-378 的整包 dump 替换为：

```python
        position = platform._find_text_position(image_bytes, actual_text, "exact", index)

        # OCR 查找失败时打一行可读摘要（识别条数即可判断"没识别到"还是"识别了但不对"）
        if position is None and platform.ocr_client:
            failure = self._get_last_failure(platform) or {}
            logger.warning(
                f"OCR find text failed: target=\"{text}\", "
                f"reason={failure.get('not_found_reason')}, error={failure.get('error')}"
            )

        return position
```

（`_find_text_position` :274-302 无 dump，不改。）

- [ ] **Step 5: 替换 image.py / ocr.py 固定文案**

先跑 `cd D:/code/autotest && grep -n "Image not found\|Text not found" worker/actions/image.py worker/actions/ocr.py` 获得实际站点清单（基线：image.py 错误文案 :72、:274、:405、:475，near text :335；ocr.py :68、:135、:417、:480；`image.py:268` 的 `output="Image not found as expected"` 是**成功语义**的输出，不改）。逐站点按所属 kind 应用：

image.py 错误返回统一改为（以 :67-75 `image_click` 为例，其余站点同型替换——保留各站点原有的 `ocr_info`/`region_screenshot`/时间戳等字段不动，只换 error 与新增 error_type）：

```python
        if not position:
            error_msg, error_type = format_find_failure(
                self._get_last_failure(platform), action.image_path or "模板图片",
                threshold=threshold, index=index, kind="image",
            )
            return ActionResult(
                number=0,
                action_type=self.name,
                status=ActionStatus.FAILED,
                error=error_msg,
                error_type=error_type,
                ocr_info=self._get_last_ocr_info(platform),
                region_screenshot=_region_b64(screenshot, bool(action.region)),
            )
```

说明：若站点上下文中目标可用变量名不是 `action.image_path`（如近文本站点用 `action.value`），用该站点实际的目标变量；`format_find_failure` 的 import 加在各文件头部 `from worker.actions.failure import format_find_failure`。

ocr.py 文本站点统一改为（以 :68 为例）：

```python
        if not position:
            error_msg, error_type = format_find_failure(
                self._get_last_failure(platform), action.value,
                index=index, kind="text",
            )
            return ActionResult(
                number=0,
                action_type=self.name,
                status=ActionStatus.FAILED,
                error=error_msg,
                error_type=error_type,
                ocr_info=self._get_last_ocr_info(platform),
            )
```

（文本类不传 threshold——文本没有相似度概念。）

5c. worker 本地失败补 `error_type="其他"`：`image.py` 中所有 `image_base64 is required` 分支（grep `image_base64 is required` worker/actions/image.py，基线 8 处 :47-53 等）统一改为：

```python
        if not action.image_base64:
            return ActionResult(
                number=0,
                action_type=self.name,
                status=ActionStatus.FAILED,
                error="image_base64 is required",
                error_type="其他",
            )
```

- [ ] **Step 6: 运行确认通过**

Run: `cd D:/code/autotest && venv/Scripts/python -m pytest tests/actions/ -v`
Expected: 全部 PASS（若既有用例断言了旧英文文案，按新中文文案更新断言）

- [ ] **Step 7: 提交**

```bash
cd D:/code/autotest && git add worker/actions/failure.py worker/actions/base.py worker/actions/image.py worker/actions/ocr.py tests/actions/test_failure_format.py && git commit -m "feat(actions): find 类失败统一中文文案与失败类型，日志不再倾倒原始响应"
```

### Task 7: 结果模型 error_type + 任务层透传 + 日志脱敏补漏

**Files:**
- Modify: `D:\code\autotest\worker\task\result.py`（ActionResult :33-111、TaskResult :114-190）
- Modify: `D:\code\autotest\worker\worker.py:1290`（failed_result 透传）
- Modify: `D:\code\autotest\worker\server.py:386-401`（_format_action_results 脱敏）
- Test: `D:\code\autotest\tests\task\test_result_error_type.py`（新建）

**Interfaces:**
- Consumes: Task 6 写入 `ActionResult.error_type`
- Produces: `ActionResult.error_type: str | None`、`TaskResult.error_type: str | None`（to_dict 非 None 才输出，from_dict 读取）——testcase 侧（Task 9）读取 `result.error_type`。日志中 `region_screenshot` 被 `<base64_data>` 替换。

- [ ] **Step 1: 写失败测试**

创建 `D:\code\autotest\tests\task\test_result_error_type.py`：

```python
"""error_type 字段序列化与任务透传测试。"""

from worker.task.result import ActionStatus, ActionResult, TaskResult, TaskStatus


def test_action_result_error_type_roundtrip():
    ar = ActionResult(number=0, action_type="image_click", status=ActionStatus.FAILED,
                      error="未找到目标图片", error_type="相似度不足")
    d = ar.to_dict()
    assert d["error_type"] == "相似度不足"
    assert ActionResult.from_dict(d).error_type == "相似度不足"


def test_action_result_none_error_type_not_serialized():
    ar = ActionResult(number=0, action_type="click", status=ActionStatus.SUCCESS)
    assert "error_type" not in ar.to_dict()


def test_task_result_error_type_roundtrip():
    tr = TaskResult(status=TaskStatus.FAILED, platform="windows", error="e", error_type="文本未找到")
    d = tr.to_dict()
    assert d["error_type"] == "文本未找到"
    assert TaskResult.from_dict(d).error_type == "文本未找到"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/code/autotest && venv/Scripts/python -m pytest tests/task/test_result_error_type.py -v`
Expected: FAIL（`error_type` 不是合法字段）

- [ ] **Step 3: 实现**

3a. `D:\code\autotest\worker\task\result.py` `ActionResult`：在 `error: str | None = None`（:43）之后加 `error_type: str | None = None  # 失败类型（8 词词汇表，见 worker/actions/failure.py）`；`from_dict`（:59-78）在 `error=data.get("error"),` 之后加 `error_type=data.get("error_type"),`；`to_dict`（:80-111）在 `if self.error is not None:` 块之后加：

```python
        if self.error_type is not None:
            result["error_type"] = self.error_type
```

3b. 同文件 `TaskResult`：在 `error: str | None = None`（:129）之后加 `error_type: str | None = None`；`from_dict`（:140-155）与 `to_dict`（:157-190）按同样方式各加一行（from_dict 在 `error=data.get("error"),` 后加 `error_type=data.get("error_type"),`；to_dict 在 error 块后加同 3a 的两行）。

3c. `D:\code\autotest\worker\worker.py:1290` `failed_result = TaskResult(...)` 中 `error=result.error,` 之后加 `error_type=result.error_type,`。

3d. `D:\code\autotest\worker\server.py` `_format_action_results`（:394-399）改为：

```python
    formatted = []
    for action in actions:
        result = action.copy()
        # 替换截图字段（region_screenshot 同样是 base64，必须一并脱敏）
        if result.get("screenshot"):
            result["screenshot"] = "<base64_data>"
        if result.get("region_screenshot"):
            result["region_screenshot"] = "<base64_data>"
        formatted.append(result)
```

3e. 各平台 `execute_action` 的兜底 `except Exception`（`worker/platforms/windows.py:529-537`，以及 web.py / harmony.py / android.py / ios.py / mac.py 中同构分支——grep `except Exception as e:` 各平台 execute_action 内定位）补 `error_type="其他"`：

```python
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ActionResult(
                number=0,
                action_type=action.action_type,
                status=ActionStatus.FAILED,
                duration_ms=duration_ms,
                error=str(e),
                error_type="其他",
            )
```

（`ActionCancelledError/ActionTimedOutError` 的 re-raise 分支在它之前，不受影响。）

- [ ] **Step 4: 运行确认通过**

Run: `cd D:/code/autotest && venv/Scripts/python -m pytest tests/task/ tests/actions/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
cd D:/code/autotest && git add worker/task/result.py worker/worker.py worker/server.py tests/task/test_result_error_type.py && git commit -m "feat(result): ActionResult/TaskResult 增加 error_type，日志脱敏补 region_screenshot"
```

---

## Phase 3: testcase（D:\code\testcase）

### Task 8: 本地模板缺失富诊断 + error_type 落到报告数据

**Files:**
- Modify: `D:\code\testcase\common\utils.py`（追加 `find_similar_templates`）
- Modify: `D:\code\testcase\aw\base_aw.py`（`_load_image_as_base64` :993 附近追加 `_load_template_or_raise`；10 处 raise :902/:975/:1394/:1418/:1439/:1461/:1487/:1510/:1535/:1559；wrapper error_type :255-258；`_execute_sync` full_result :597-613）
- Test: `D:\code\testcase\tests\unit\test_template_loader.py`（新建）

**Interfaces:**
- Consumes: 无（纯本地）
- Produces:
  - `common.utils.find_similar_templates(image_path: str, images_root: Path, max_n: int = 3) -> list[str]`
  - `BaseAW._load_template_or_raise(image_path: str) -> str`（失败抛富信息 FileNotFoundError，首行 `图片文件不存在: <path>`）
  - 业务方法失败日志 `result.error_type`：本地缺失为 `"文件缺失"`；worker 失败透传 worker 返回的 `error_type`（Task 7 提供）。

- [ ] **Step 1: 写失败测试**

创建 `D:\code\testcase\tests\unit\test_template_loader.py`：

```python
"""模板缺失富诊断测试。"""

from pathlib import Path

import pytest

from common.utils import find_similar_templates


def _make_images(root: Path):
    (root / "web").mkdir(parents=True)
    (root / "web" / "摄像头_关闭.png").write_bytes(b"png")
    (root / "web" / "摄像头_开启_新.png").write_bytes(b"png")
    (root / "web" / "会中_挂断.png").write_bytes(b"png")


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
        (tmp_path / "web" / f"摄像头_开启_{i}.png").write_bytes(b"png")
    matches = find_similar_templates("images/web/摄像头_开启.png", tmp_path)
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/code/testcase && python -m pytest tests/unit/test_template_loader.py -v`
Expected: FAIL（`find_similar_templates`/`_load_template_or_raise` 不存在）

- [ ] **Step 3: 实现**

3a. `D:\code\testcase\common\utils.py` 末尾追加（文件头 import 区补 `import difflib`）：

```python
def find_similar_templates(image_path: str, images_root: Path, max_n: int = 3) -> list[str]:
    """在 images_root 下找与 image_path 最相近的模板文件。

    Args:
        image_path: 目标图片路径（取文件名做相近度匹配）。
        images_root: 模板根目录（通常是 <项目根>/images）。
        max_n: 最多返回条数。

    Returns:
        list[str]: 形如 "images/web/摄像头_关闭.png（相似 0.91）" 的提示列表。
    """
    if not images_root.exists():
        return []
    name = os.path.basename(image_path)
    stem = os.path.splitext(name)[0]
    candidates = [
        str(p.relative_to(images_root))
        for p in images_root.rglob("*")
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp")
    ]
    if not candidates:
        return []
    basenames = [os.path.basename(c) for c in candidates]
    close = difflib.get_close_matches(name, basenames, n=max_n, cutoff=0.6)
    result = []
    for m in close:
        for rel in candidates:
            if os.path.basename(rel) == m:
                ratio = difflib.SequenceMatcher(None, stem, os.path.splitext(m)[0]).ratio()
                result.append(f"{rel}（相似 {ratio:.2f}）")
                break
    return result
```

3b. `D:\code\testcase\aw\base_aw.py`：文件 import 区补 `from common import utils`（若已有 `from common.utils import load_image_as_base64` 保持不动；**必须经 `utils.` 模块属性取 get_project_root/find_similar_templates，单测的 monkeypatch 才生效**），并确认 `import os` 已有。在 `_load_image_as_base64`（:993）方法之后追加：

```python
    def _load_template_or_raise(self, image_path: str) -> str:
        """加载模板图片 base64；文件不存在时抛出带定位信息的 FileNotFoundError。"""
        base64_str = self._load_image_as_base64(image_path)
        if base64_str:
            return base64_str
        root = utils.get_project_root()
        full_path = image_path if os.path.isabs(image_path) else root / image_path
        lines = [
            f"图片文件不存在: {image_path}",
            f" ↳ 绝对路径: {full_path}（项目根: {root}）",
        ]
        similar = utils.find_similar_templates(image_path, root / "images")
        if similar:
            lines.append(" ↳ images/ 下相近文件: " + "、".join(similar))
        raise FileNotFoundError("\n".join(lines))
```

3c. 10 处 raise（grep `图片文件不存在` 确认：:902、:975、:1394、:1418、:1439、:1461、:1487、:1510、:1535、:1559）逐站点把

```python
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
```

替换为

```python
        image_base64 = self._load_template_or_raise(image_path)
```

（各站点局部变量名/缩进以现场为准，两行模式一致。）

3d. wrapper 错误日志（:255-258）改为：

```python
                error_result = {
                    "error": str(e),
                    "error_type": "文件缺失" if isinstance(e, FileNotFoundError) else type(e).__name__,
                }
```

3e. `_execute_sync` 的 full_result（:597-613）在 `if "ocr_info" in action_result:` 块之后追加：

```python
        if action_result.get("error_type"):
            # 失败类型（worker 生成或本地"文件缺失"），报告据此渲染类型徽章
            full_result["error_type"] = action_result["error_type"]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd D:/code/testcase && python -m pytest tests/unit/test_template_loader.py tests/unit/test_report_generator.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
cd D:/code/testcase && git add common/utils.py aw/base_aw.py tests/unit/test_template_loader.py && git commit -m "feat(aw): 模板文件缺失时给出绝对路径与相近文件提示，error_type 落报告数据"
```

### Task 9: 报告渲染类型徽章 / 空识别提示 / 目标图片占位块

**Files:**
- Modify: `D:\code\testcase\common\report_generator.py`（`_CSS` :1033-1347 追加样式；`_render_row_detail` :466-580）
- Test: `D:\code\testcase\tests\unit\test_report_generator.py`（追加用例）

**Interfaces:**
- Consumes: Task 8 的 `log.result.error_type`、`log.target_image_path`
- Produces: 失败行详情的最终视觉呈现（与已批准的效果图一致）。无 `error_type` 的数据渲染与现状完全一致（回退）。

- [ ] **Step 1: 写失败测试**

在 `D:\code\testcase\tests\unit\test_report_generator.py` 末尾追加：

```python
def _fail_log(**extra):
    """构造失败 aw_call 行日志基线。"""
    log = {
        "type": "aw_call",
        "method": "image_click",
        "args": {},
        "success": False,
        "result": {"error": "未找到目标图片\"x.png\"：最高相似度 0.72，低于阈值 0.90"},
        "request_id": "abc123",
    }
    log.update(extra)
    return log


def test_error_type_renders_badge():
    log = _fail_log(result={"error": "e", "error_type": "相似度不足"})
    html = HTMLReportGenerator._render_row_detail(log)
    assert 'type-badge t-amber' in html
    assert '相似度不足' in html


def test_error_type_service_error_is_red():
    log = _fail_log(result={"error": "boom", "error_type": "OCR服务错误"})
    html = HTMLReportGenerator._render_row_detail(log)
    assert 'type-badge t-red' in html


def test_unknown_error_type_falls_back_gray():
    log = _fail_log(result={"error": "e", "error_type": "某种新类型"})
    html = HTMLReportGenerator._render_row_detail(log)
    assert 'type-badge t-gray' in html


def test_no_error_type_renders_plain():
    """无 error_type（旧数据）保持现状，无徽章。"""
    html = HTMLReportGenerator._render_row_detail(_fail_log())
    assert 'type-badge' not in html
    assert '未找到目标图片' in html


def test_empty_ocr_info_hint_on_failure():
    log = _fail_log(result={"error": "e", "error_type": "文本未找到", "ocr_info": []})
    html = HTMLReportGenerator._render_row_detail(log)
    assert 'OCR 未识别到任何文字' in html


def test_empty_ocr_hint_skipped_for_non_find_methods():
    """非 find 类失败（如 assert）不显示空识别提示。"""
    log = _fail_log(method="assert_check", result={"error": "断言失败"})
    html = HTMLReportGenerator._render_row_detail(log)
    assert 'OCR 未识别到任何文字' not in html


def test_text_method_failure_uses_recognized_label():
    """ocr_* 失败时标签为"屏幕实际识别到"（与已批准效果图一致）。"""
    log = _fail_log(
        method="ocr_wait",
        result={"error": "e", "error_type": "文本未找到",
                "ocr_info": [{"text": "会议加载中", "center": {"x": 512, "y": 300}}]},
    )
    html = HTMLReportGenerator._render_row_detail(log)
    assert '屏幕实际识别到' in html


def test_target_image_missing_placeholder():
    log = _fail_log(
        target_image="",
        target_image_path="images/web/摄像头_开启.png",
        result={"error": "e", "error_type": "文件缺失"},
    )
    html = HTMLReportGenerator._render_row_detail(log)
    assert '目标图片缺失' in html
    assert 'images/web/摄像头_开启.png' in html


def test_target_image_present_still_renders_img():
    """target_image 有 base64 时保持原图片渲染，不出占位块。"""
    log = _fail_log(
        target_image="a" * 200,
        target_image_path="images/web/x.png",
        result={"error": "e"},
    )
    html = HTMLReportGenerator._render_row_detail(log)
    assert '目标图片' in html
    assert '目标图片缺失' not in html
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/code/testcase && python -m pytest tests/unit/test_report_generator.py -v`
Expected: 新增 9 个用例 FAIL（无 `type-badge`/占位块/提示/新标签），既有用例 PASS

- [ ] **Step 3: 实现**

3a. `_CSS`（:1033-1347）末尾（`/* ── 过滤态 ──` 区块之前）追加：

```css
/* ── 失败类型徽章 / 目标图片缺失占位（新增） ── */
.type-badge { display:inline-flex; align-items:center; gap:5px; padding:2px 9px; border-radius:6px; font-size:11px; font-weight:700; margin:2px 0 6px; }
.type-badge.t-amber { background:#fef3c7; color:#b45309; }
.type-badge.t-orange { background:#ffedd5; color:#c2410c; }
.type-badge.t-red { background:#fee2e2; color:#dc2626; }
.type-badge.t-gray { background:#f1f5f9; color:#475569; }
.shot-missing { width:168px; height:104px; border:1.5px dashed #cbd5e1; border-radius:8px; background:#f8fafc; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:5px; padding:8px; text-align:center; }
.shot-missing .m1 { font-size:10.5px; font-weight:600; color:#94a3b8; }
.shot-missing .m2 { font-family:var(--mono); font-size:9.5px; color:#94a3b8; word-break:break-all; line-height:1.3; }
.ocr-empty-hint { font-size:11.5px; color:#94a3b8; font-family:var(--mono); }
```

3b. `HTMLReportGenerator` 类属性区（`_CSS` 定义之前或类内常量区）追加映射：

```python
    # 失败类型 → 徽章配色（词汇表与 worker/actions/failure.py 对齐；未收录词回退灰）
    _TYPE_BADGE_STYLES = {
        "文件缺失": "t-orange",
        "OCR服务错误": "t-red",
        "OCR请求失败": "t-red",
        "文本未找到": "t-amber",
        "相似度不足": "t-amber",
        "颜色校验未通过": "t-amber",
        "距离超限": "t-amber",
    }
```

3c. `_render_row_detail` 错误块（:476-484）替换为：

```python
        # 错误信息（含失败类型徽章；无 error_type 的旧数据保持平文本）
        if not success:
            error_msg = result.get("error", "")
            if error_msg:
                clean_err = HTMLReportGenerator._clean_text_for_display(str(error_msg))
                rid = f'<div class="rid">request_id: {_esc(request_id)}</div>' if request_id else ""
                error_type = result.get("error_type", "")
                badge = ""
                if error_type:
                    style = HTMLReportGenerator._TYPE_BADGE_STYLES.get(error_type, "t-gray")
                    badge = f'<span class="type-badge {style}">🏷️ {_esc(error_type)}</span>'
                parts.append(
                    f'<div class="err-box"><div class="k">错误信息</div>{badge}'
                    f'<div class="v">{_esc(clean_err)}</div>{rid}</div>'
                )
```

3d. OCR 块（:538-552）替换为（失败时标签按已批准效果图：文本类 ocr_* 方法显示"屏幕实际识别到"，其余保持"OCR 识别结果"；空识别提示仅对 find 类方法显示，避免 click/assert 等普通失败误标）：

```python
        # OCR 识别结果：有数据即显示（不再按方法名白名单门控）
        ocr_info = result.get("ocr_info", [])
        is_find_method = str(log.get("method", "")).startswith(("ocr_", "image_"))
        if isinstance(ocr_info, list) and ocr_info:
            chips = []
            for item in ocr_info:
                if not isinstance(item, dict):
                    continue
                text = item.get("text", "")
                center = item.get("center", {})
                x = center.get("x", "-") if isinstance(center, dict) else "-"
                y = center.get("y", "-") if isinstance(center, dict) else "-"
                if text:
                    chips.append(f'<span class="ocr-chip">"{_esc(text)}" ({_esc(x)}, {_esc(y)})</span>')
            if chips:
                label = "屏幕实际识别到" if (not success and str(log.get("method", "")).startswith("ocr_")) else "OCR 识别结果"
                parts.append(f'<div class="ocr-box"><div class="k">{label}</div><div>{"".join(chips)}</div></div>')
        elif not success and is_find_method:
            parts.append('<div class="ocr-box"><div class="k">OCR 识别结果</div><div class="ocr-empty-hint">OCR 未识别到任何文字</div></div>')
```

3e. 截图块（:554-576）`target_image` 分支改为：

```python
            target_image = log.get("target_image", "")
            if target_image and len(target_image) > 100:
                shots.append(
                    f'<div class="shot" onclick="showImage(this.querySelector(\'img\').src);event.stopPropagation()">'
                    f'<img src="data:image/png;base64,{target_image}"><span class="cap">目标图片</span></div>'
                )
            elif log.get("target_image_path"):
                # 模板文件缺失/未加载：用占位块替代空白，明示"没发出去"而不是"没匹配上"
                shots.append(
                    f'<div class="shot-missing"><span class="m1">⬚ 目标图片缺失</span>'
                    f'<span class="m2">{_esc(log.get("target_image_path"))}</span></div>'
                )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd D:/code/testcase && python -m pytest tests/unit/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 生成一次人工目检报告（可选但推荐）**

用 demo 数据走一遍 `HTMLReportGenerator.generate`，浏览器打开确认与效果图一致（徽章配色、占位块、chips）。若无可用的最小数据构造，跳过此步——单测已覆盖渲染片段。

- [ ] **Step 6: 提交**

```bash
cd D:/code/testcase && git add common/report_generator.py tests/unit/test_report_generator.py && git commit -m "feat(report): 失败类型徽章/空识别提示/目标图片缺失占位块"
```

### Task 10: 收尾——spec 状态更新 + 三仓库回归

**Files:**
- Modify: `D:\code\testcase\docs\superpowers\specs\2026-11-12-image-not-found-reason-report-design.md`（frontmatter status）

**Interfaces:**
- Consumes: Task 1-9 全部完成
- Produces: 归档状态的设计文档 + 全量回归绿

- [ ] **Step 1: 全量回归**

```bash
cd D:/code/ocr_service && venv/Scripts/python -m pytest tests/ -v
cd D:/code/autotest && venv/Scripts/python -m pytest tests/ -v
cd D:/code/testcase && python -m pytest tests/unit/ -v
```
Expected: 三个仓库全绿（autotest 若有无设备依赖的预存在失败，逐条确认与本计划无关后记录跳过）

- [ ] **Step 2: spec 状态更新**

把 `docs/superpowers/specs/2026-11-12-image-not-found-reason-report-design.md` frontmatter 的 `status: draft` 改为 `status: approved`。

- [ ] **Step 3: 提交**

```bash
cd D:/code/testcase && git add docs/superpowers/specs/2026-11-12-image-not-found-reason-report-design.md && git commit -m "docs: 设计文档定稿（已实现）"
```
