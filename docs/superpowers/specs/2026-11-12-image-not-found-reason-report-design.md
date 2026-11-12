---
title: 图片找不到时报告呈现失败原因
date: 2026-11-12
status: draft
---

# 图片找不到时报告呈现失败原因

## 背景

数据流：testcase (pytest) → autotest worker → ocr_service → 原路返回 → HTML 报告。
用户反馈："图片找不到"类错误在报告里只有一句平文本或一坨 traceback，无法定位**为什么**找不到。

实际上"找不到"有 8 种完全不同的原因，目前全部坍缩成两种形态：

| # | 真实原因 | 当前表现 |
|---|---------|---------|
| 1 | 模板文件在 testcase 本地不存在 | 裸 `FileNotFoundError: 图片文件不存在: xxx`（10 处重复 raise，无绝对路径、无相近文件提示） |
| 2 | OCR 服务不可达 / 非 200 | `Image not found`（HTTP 状态码与响应体在 `ocr_client._post` 中丢失） |
| 3 | OCR 服务内部错误（base64 解码失败 / paddlex 推理异常） | 同上；服务端无错误码，全部 `str(e)` |
| 4 | 屏幕上没识别到任何文字 | 同上 |
| 5 | 识别到文字但目标文本不在其中 | 同上（`ocr_info` 有数据但未与失败原因关联） |
| 6 | 图像匹配低于阈值 | 同上（最佳置信度在 `image_matcher.py:180-201` 已算出，只写日志不进响应） |
| 7 | 灰度通过但颜色校验失败 | 同上 |
| 8 | match_near_text：文字没找到 / 模板没匹配 / 距离超限 | 三种情况响应形态完全相同 |

关键丢失点（本次要打通的堵点）：

- **ocr_service**：响应无 `error_code`/错误分类；未命中一律 `status=success + 空数组`；`best_confidence`/`threshold` 不回显；`get_coord_by_text` 引擎报错被吞成 success+空（`routes.py:206-213`）；`decode_image` 三种失败共用一句 "Failed to decode image"（`image_utils.py:29-30`）。
- **autotest worker**：`common/ocr_client.py:183-185, 241-243, 330-332, 438-440` 服务错误原因只写 warning 日志后丢弃，返回 `None/[]`；`_post`（:498-507）非 200 时 HTTP 状态码和响应体丢失；`worker/actions/image.py:72` 等 ~15 处固定文案不带阈值/最佳相似度等上下文；`worker/task/result.py` 的 `ActionResult/TaskResult` 只有一个平文本 `error` 字段；`server.py:386-400` 响应日志脱敏漏掉 `region_screenshot`（整段 base64 进日志）。
- **testcase**：行级 err-box 渲染平文本（`report_generator.py:476-484`）；`target_image` 缺失时连占位提示都没有（:570-574），看不出"没匹配上"还是"文件不存在"；页首错误框只有完整 traceback（:954-964）。

## 目标

1. "图片找不到"时，报告能直接给出**分类原因 + 关键数值**（如：最高相似度 0.72 低于阈值 0.90）。
2. 本地模板文件缺失时，给出绝对路径、`images/` 下相近文件、排查建议。
3. 服务错误与"正常未找到"在报告里可区分（徽章颜色 + 错误码）。
4. 全链路增量改动，新旧版本混布不破坏（旧字段 `error` 字符串保留）。

## 范围

- **ocr_service**：响应 schema 增量字段、错误分类、未命中诊断、修吞错误 bug。不改接口路径、不改既有字段语义。
- **autotest worker**：诊断沿现有线程本地模式透传，动作层拼装可读错误文案，结果模型增加字段。
- **testcase**：模板加载统一报错、报告渲染分类徽章/数值/占位块。
- 不改动：aw 动作清单、执行流程、报告整体版式（只增强错误呈现区域）。

## 错误码总表（三仓库共用一份定义，各自文档留副本）

| error_code | 产生层 | 含义 | 人类可读消息（示例） |
|---|---|---|---|
| TEMPLATE_FILE_MISSING | testcase | 模板文件不存在 | 图片文件不存在: images/web/会中_挂断.png |
| IMAGE_BASE64_REQUIRED | worker | 动作未传模板图 | image_base64 is required |
| TEMPLATE_DECODE_FAILED | worker | 模板 base64 解码失败 | 模板图片解码失败: Invalid base64... |
| SCREENSHOT_FAILED | worker | 截图失败（设备离线等） | 截图失败: 设备未找到: xxx |
| REGION_INVALID | worker | region 参数非法 | Invalid region: x1 must be < x2 |
| HTTP_ERROR | worker | OCR 服务不可达 / 非 200 | OCR 服务请求失败: HTTP 503 (重试 2 次后) |
| IMAGE_EMPTY | ocr_service | 空图片 | 图片数据为空 |
| IMAGE_DECODE_FAILED | ocr_service | base64 非法/损坏/格式不支持 | 图片解码失败（共 N 字节） |
| OCR_ENGINE_ERROR | ocr_service | OCR 推理异常 | OCR 引擎错误: \<异常摘要\> |
| TEMPLATE_LARGER_THAN_SOURCE | ocr_service | 模板大于源图 | 模板(200x150) 大于源图(180x140) |
| TEXT_NOT_FOUND | 服务→worker | 屏幕无目标文本 | 未找到文本 "密码"（识别到 5 个文本，最相近: "用户名"...） |
| MATCH_BELOW_THRESHOLD | 同上 | 灰度低于阈值 | 最高相似度 0.72 低于阈值 0.90 |
| COLOR_CHECK_FAILED | 同上 | 灰度过、颜色不过 | 灰度相似度 0.95 达标，但颜色校验未通过 |
| DISTANCE_EXCEEDED | 同上 | 候选距文本超限 | 最近候选距离 812px 超过上限 500px |
| INTERNAL_ERROR | 兜底 | 未分类异常 | 内部错误: \<异常摘要\> |

`not_found_reason` 枚举（ocr_service，`status=success` 且结果为空时返回）：
`below_threshold` / `color_check_failed` / `no_text_recognized` / `text_not_found` / `template_not_matched` / `distance_exceeded`。

## 设计方案

### 1. ocr_service：源头把原因说清楚（全部增量字段）

**响应 schema 增量**（`api/schemas.py`，四个响应模型统一增加，均可选）：

```python
error_code: str | None = None          # status="error" 时的错误码（上表枚举）
not_found_reason: str | None = None    # status="success" 且结果为空时的原因
best_confidence: float | None = None   # 匹配类接口：最高灰度/特征分
threshold: float | None = None         # 实际生效阈值回显
nearest_distance: float | None = None  # 仅 match_near_text：最近候选距离
```

**改动点**：

1. `utils/image_utils.py:12-32` `decode_image` 细分异常：空字符串 → `IMAGE_EMPTY`；非法 base64 / `cv2.imdecode` 返回 None → `IMAGE_DECODE_FAILED`（消息带字节数）；并实现 yaml 声称支持但代码未做的 `data:image/...;base64,` 前缀剥离。
2. `api/routes.py` 统一包装：推理/匹配异常 → `status="error"` + `error_code=OCR_ENGINE_ERROR`，`error` 字段保留异常摘要。
3. **修吞错误 bug**：`routes.py:206-213` `get_coord_by_text` 引擎出错时由 `success+空` 改为 `status="error"` + `error_code=OCR_ENGINE_ERROR`。旧 worker 对非 success 本来就按失败处理（返回 None → "Text not found"），无回归。
4. `/image/match`：`image_matcher.py:180-201` 已算出的灰度分与位置写入响应——低于阈值时 `not_found_reason=below_threshold` + `best_confidence` + `threshold` 回显；颜色关失败 → `color_check_failed`（`best_confidence` 填灰度分）；模板大于源图 → `status="error"` + `error_code=TEMPLATE_LARGER_THAN_SOURCE`（旧 worker 兼容性同上：非 success 与空 matches 结果等价）。
5. `/image/match_near_text`（`routes.py:428-481`）：三种失败分别标 `text_not_found` / `template_not_matched` / `distance_exceeded`，距离超限时附 `nearest_distance`。
6. `ocr_api.yaml` 同步新字段，并修正 data-URI 前缀的失实描述。

### 2. autotest worker：不再丢信息，拼出人话

**诊断沿现有线程本地模式透传**（对标 `_last_response`/`get_last_ocr_info`，`common/ocr_client.py:129-150, 523-530`）：

1. `OCRClient` 增加线程本地 `_last_failure`，4 个方法（`recognize`/`find_text`/`match_image`/`match_near_text`）在"服务错误 / HTTP 错误 / 正常未找到"三种结局时填入 `{error_code, error, not_found_reason, best_confidence, threshold, nearest_distance}`；每次调用开头重置。新增 `get_last_failure()` 访问器；`_post` 最终失败返回体增加 `error_code="HTTP_ERROR"` 与 `http_status`。
2. 新增 `worker/actions/failure.py`：`format_find_failure(failure, target, threshold, index)` → 返回 `(error_message, error_code, error_details)`，消息按上表"人类可读消息"列拼装，`error_details` 携带 `{threshold, best_confidence, target, index, request_id, recognized_sample}`。
3. 动作层替换固定文案：`worker/actions/image.py:72,182,274,335,405,475,582` 与 `worker/actions/ocr.py:68,242,307,344,417,480,555,587,666` 的 `"Image not found"/"Text not found: X"` 改为 `format_find_failure(self._get_last_failure(platform), ...)`——`_get_last_failure` 是 `BaseActionExecutor` 新增访问器，对标现有 `_get_last_ocr_info`（find 助手 `worker/actions/base.py:304-337, 339-380` 失败时本就会读 `ocr_client` 的 last_response，取数路径一致）。
4. worker 本地失败分类：`image_base64` 缺失 → `IMAGE_BASE64_REQUIRED`（`image.py:47-53` 等 8 处）；`execute_action` 的 `except Exception` 兜底（`platforms/windows.py:534-540` 及各平台同构）按异常类型映射 `TEMPLATE_DECODE_FAILED` / `REGION_INVALID` / `SCREENSHOT_FAILED`，未命中映射的归 `INTERNAL_ERROR`，`error` 保留 `str(e)`。
5. 结果模型增量字段（`worker/task/result.py`）：`ActionResult` 与 `TaskResult` 增加 `error_code: str | None = None`、`error_details: dict | None = None`，`to_dict`/`from_dict` 同步（None 不序列化，旧客户端无感）。
6. 任务层透传（`worker/worker.py:1282-1293`）：首个失败 action 的 `error_code/error_details` 原样上移到 `TaskResult`。
7. 日志脱敏补漏：`server.py:386-400` `_format_action_results` 把 `region_screenshot` 纳入脱敏（与 `screenshot` 同待遇）。

### 3. testcase：本地诊断 + 报告呈现

**本地模板缺失诊断**：

1. `aw/base_aw.py` 新增统一辅助函数 `_load_template_or_raise(image_path)`：内部调 `common/utils.py load_image_as_base64`，失败时 raise 富信息 `FileNotFoundError`：

   ```
   图片文件不存在: images/web/会中_挂断.png
    ↳ 绝对路径: D:\code\testcase\images\web\会中_挂断.png（项目根 D:\code\testcase）
    ↳ images/ 下相近文件: 会中_挂断按钮.png（相似 0.87）、会中_挂断_new.png（相似 0.85）
    ↳ 建议: 核对文件名大小写/扩展名，或补充模板
   ```

   相近文件用 `difflib.get_close_matches` 扫描 `images/**`，最多 3 条。10 处重复 raise（`base_aw.py:902, 975, 1373, 1397, 1418, 1440, 1466, 1489, 1514, 1538`）全部替换为调用该函数。
2. `AWError`（`base_aw.py:30-37`）消息格式不变；`_execute_sync` 的 `full_result` 组装（:561-613）透传 `error_code/error_details`（worker 返回的 `ActionResult.to_dict` 已含新字段，自然流入 `log_aw_call` 的 result）。

**报告渲染**（`common/report_generator.py`，四处增强，均向后兼容）：

1. 行级 err-box（:476-484）：`result.error_code` 存在时，在错误文本上方渲染分类徽章（错误码中文名）+ 数值详情块（相似度进度条 `▓▓▓░░ 0.72 / 阈值 0.90`、`nearest_distance`、`request_id`）；无 `error_code` 时维持现有平文本。
2. OCR 提示（:539-552 chips 保留）：失败且 `ocr_info` 为空时显示"OCR 未识别到任何文字"。
3. 目标图片占位（:570-574）：`target_image` 缺失但有 `target_image_path` 时，渲染灰色虚线占位块"目标图片缺失: {path}"（区别于"未匹配到"）。
4. 页首错误框与"首个失败步骤"（:954-964）：traceback 上方增加"失败原因摘要"行——取 `error_code` 分类 + 一行原因；无分类时从 `error_type`（wrapper 已记录，`base_aw.py:255-276`）推断"文件缺失/断言失败"等粗分类。完整堆栈折叠保留。

**徽章配色**：文件缺失=橙、服务错误=红、未找到/未匹配=琥珀、其他=灰。

### 报告效果示意

行级失败卡片：

```
▶ 第 3 步  image_click("会中_挂断.png")   ❌ 失败  1.2s
   ┌──────────────────────────────────────────────────────┐
   │ 🏷️ 图像未匹配 (MATCH_BELOW_THRESHOLD)                │
   │ 未找到目标图片：最高相似度 0.72 低于阈值 0.90          │
   │ 相似度  ▓▓▓▓▓▓▓░░░  0.72 / 阈值 0.90                 │
   │ OCR 识别结果: [离开会议] [录制] [更多] [邀请]          │
   │ [当前屏幕] [查找区域] [目标图片]                       │
   │ request_id: a1b2c3                                   │
   └──────────────────────────────────────────────────────┘
```

页首错误框：

```
❌ 失败原因摘要: 图像未匹配 — 最高相似度 0.72 低于阈值 0.90（目标: images/web/会中_挂断.png）
   ▸ 展开完整堆栈
```

## 兼容性

- 所有新 JSON 字段可选：旧 worker 忽略 ocr_service 新字段；旧 testcase 忽略 worker 新字段；报告端无 `error_code` 自动回退平文本。
- `error` 字符串字段保留（内容更丰富），不做字段改名/删除。
- 行为变化仅两处（均对旧端无回归，旧端本就按失败处理）：
  1. `get_coord_by_text` 引擎错误：success+空 → status="error"；
  2. `/image/match` 模板大于源图：success+空 → status="error"。

## 测试计划

- **ocr_service**（当前错误路径 0 覆盖）：空图/非法 base64/损坏图 → 断言 `error_code`；低于阈值 → 断言 `not_found_reason/best_confidence/threshold`；颜色关失败、模板过大、near_text 三种失败 → 断言对应字段；data-URI 前缀剥离。
- **autotest**：`get_last_failure` 透传单测；`format_find_failure` 文案与 details 单测；更新断言 `"Image not found"` 固定文案的既有用例；`result.py` 新字段序列化往返测试。
- **testcase**：`tests/unit/test_report_generator.py` 回归 + 新增：徽章渲染、相似度进度条、占位块、无 error_code 回退、摘要行；`_load_template_or_raise` 单测（相近文件提示）。

## 实施顺序

1. ocr_service（源头字段）→ 2. autotest worker（透传 + 文案）→ 3. testcase（渲染）。
每步独立可部署；只做前 1-2 步时报告仍回退平文本，不坏。
