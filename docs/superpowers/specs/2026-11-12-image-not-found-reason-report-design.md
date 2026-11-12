---
title: 图片找不到时报告呈现失败原因
date: 2026-11-12
status: approved
---

# 图片找不到时报告呈现失败原因

## 背景

数据流：testcase (pytest) → autotest worker → ocr_service → 原路返回 → HTML 报告。
用户反馈："图片找不到"类错误在报告里只有一句平文本或一坨 traceback，无法定位**为什么**找不到。

用户确认的核心诉求（不做错误码体系）：

1. **失败类型**可见（什么不过：文件缺失 / 服务错误 / 相似度不足 / 颜色不过 / 文本未找到）。
2. **数值对比**可见：阈值预期多少、实际多少。
3. **文本找不到时**，报告要能看到屏幕上实际识别到了什么（OCR 内容）。

关键丢失点（本次要打通的堵点）：

- **ocr_service**：`/image/match` 未命中时 `status=success + 空数组`，最佳灰度分在 `image_matcher.py:180-201` 已算出但只写日志不进响应；颜色校验失败无任何标记；`get_coord_by_text` 引擎报错被吞成 success+空（`routes.py:206-213`）。
- **autotest worker**：`common/ocr_client.py:183-185, 241-243, 330-332, 438-440` 服务错误原因只写 warning 日志后丢弃，返回 `None/[]`；`_post`（:498-507）非 200 时 HTTP 状态码丢失；`worker/actions/image.py:72` 等 ~15 处固定文案 `"Image not found"` 不带阈值/实际相似度；`worker/task/result.py` 的 `ActionResult/TaskResult` 只有一个平文本 `error` 字段；`server.py:386-400` 响应日志脱敏漏掉 `region_screenshot`（整段 base64 进日志）。
- **testcase**：行级 err-box 渲染平文本（`report_generator.py:476-484`）；`target_image` 缺失时连占位提示都没有（:570-574），看不出"没匹配上"还是"文件不存在"；本地模板缺失只有裸 `FileNotFoundError: 图片文件不存在: xxx`（10 处重复 raise，无绝对路径、无相近文件提示）。

## 目标

1. 图像匹配失败：报告显示"最高相似度 X 低于阈值 Y"（或"灰度达标但颜色校验未通过"）。
2. 文本找不到：报告显示"未找到目标文本" + OCR 实际识别到的文本列表。
3. 服务错误/请求失败与"正常未找到"可区分（类型徽章颜色不同）。
4. 本地模板文件缺失：显示绝对路径 + `images/` 下相近文件。
5. 全链路增量改动，新旧版本混布不破坏（`error` 字符串保留且更丰富）。

## 范围

- **ocr_service**：未命中响应增加 2 个可选诊断字段；修 1 个吞错误 bug。不改接口路径、不加错误码枚举。
- **autotest worker**：诊断沿现有线程本地模式透传；失败文案拼入类型与数值；结果模型加 1 个可选字段。
- **testcase**：模板加载统一报错；报告渲染类型徽章 + 富文案 + 占位块。
- 不做：错误码枚举表、`error_details` 结构化字典、跨仓库枚举同步。

## 失败类型（展示用中文短词，非枚举代码）

worker/testcase 生成，报告按词配徽章颜色，未知词回退灰色：

| 类型 | 产生场景 | 消息示例 |
|---|---|---|
| 文件缺失 | testcase 本地模板文件不存在 | 图片文件不存在: images/web/会中_挂断.png |
| OCR服务错误 | 服务返回 status=error | OCR 服务错误: \<服务 error 原文\> |
| OCR请求失败 | 连接失败 / 非 200 | OCR 请求失败: HTTP 503（已重试 2 次） |
| 文本未找到 | 屏幕上没有目标文本 | 未找到文本 "密码" |
| 相似度不足 | 图像匹配低于阈值 | 最高相似度 0.72，低于阈值 0.90 |
| 颜色校验未通过 | 灰度达标、颜色不过 | 灰度相似度 0.95 达标，但颜色校验未通过 |
| 距离超限 | near_text 候选太远 | 最近候选距离 812px，超过上限 500px |
| 其他 | 解码失败/参数缺失/未分类 | 保留原异常消息 |

## 设计方案

### 1. ocr_service：源头补 2 个诊断字段（全部可选，增量）

**未命中响应（`status=success` 且结果为空）增加**：

```python
not_found_reason: str | None = None   # below_threshold / color_check_failed /
                                      # text_not_found / template_not_matched / distance_exceeded
best_confidence: float | None = None  # 已算出的最高灰度/特征分（image_matcher.py:180-201）
nearest_distance: float | None = None # 仅 match_near_text 距离超限时
```

改动点：

1. `image_matcher.py`：未命中路径把已算出的 `max_val`（灰度分）写入响应；区分"低于阈值"（:184-201）与"颜色关不过"（:115-131，`best_confidence` 填灰度分）；模板大于源图（`match_template:165-174` 及 `match_all:255-264` 两条路径）标记 `template_not_matched`。
2. `routes.py:428-481` `match_near_text` 三种失败分别标 `text_not_found` / `template_not_matched` / `distance_exceeded`（+`nearest_distance`）。
3. **修吞错误 bug**：`routes.py:206-213` `get_coord_by_text` 引擎出错时由 `success+空` 改为 `status="error"` + 现有 `error` 字段。旧 worker 对非 success 本来就按失败处理，无回归。
4. 顺手实现 yaml 声称支持但代码未做的 `data:image/...;base64,` 前缀剥离（`image_utils.py:21-23`，3 行），避免按文档调用得到莫名的解码失败。
5. `ocr_api.yaml` 补充这 2 个新字段的说明。

解码失败/推理异常**不加错误码**：维持现有 `status="error" + error=异常原文`，worker 透传后类型标"OCR服务错误"，消息即异常原文，足够定位。

### 2. autotest worker：不再丢信息，拼出带数值的人话

**诊断沿现有线程本地模式透传**（对标 `_last_response`/`get_last_ocr_info`，`common/ocr_client.py:129-150, 523-530`）：

1. `OCRClient` 增加线程本地 `_last_failure`，4 个方法在"服务错误 / HTTP 错误 / 正常未找到"三种结局时填入 `{error, not_found_reason, best_confidence, nearest_distance, http_status}`；每次调用开头重置。新增 `get_last_failure()` 访问器；`_post` 最终失败返回体补 `http_status`。
2. 新增 `worker/actions/failure.py`：`format_find_failure(failure, target, threshold, index)` → 返回 `(error_message, error_type)`，按上表"消息示例"拼装，数值直接写进消息（阈值取动作参数，实际分取 `best_confidence`）。
3. 动作层替换固定文案：`worker/actions/image.py:72,182,274,335,405,475,582` 与 `worker/actions/ocr.py:68,242,307,344,417,480,555,587,666` 的 `"Image not found"/"Text not found: X"` 改为 `format_find_failure(self._get_last_failure(platform), ...)`——`_get_last_failure` 是 `BaseActionExecutor` 新增访问器，对标现有 `_get_last_ocr_info`（find 助手 `worker/actions/base.py:304-337, 339-380` 失败时本就会读 `ocr_client` 的 last_response，取数路径一致）。文本未找到时照旧附带 `ocr_info`（屏幕识别内容），报告已有 chips 渲染。
4. worker 本地失败：`image_base64` 缺失（`image.py:47-53` 等 8 处）与 `execute_action` 兜底 `except Exception`（`platforms/windows.py:534-540` 及各平台同构）保持现有消息文本，`error_type` 按异常归类（解码→"其他"、截图→"其他"），消息保留 `str(e)`——本次不展开分类。
5. 结果模型：`ActionResult` 与 `TaskResult` 增加 `error_type: str | None = None`（`worker/task/result.py`，`to_dict`/`from_dict` 同步，None 不序列化）；任务层透传首个失败 action 的 `error_type`（`worker/worker.py:1282-1293`）。
6. 日志脱敏补漏：`server.py:386-400` `_format_action_results` 把 `region_screenshot` 纳入脱敏（与 `screenshot` 同待遇）。

### 3. testcase：本地诊断 + 报告呈现

**本地模板缺失诊断**：

1. `aw/base_aw.py` 新增统一辅助函数 `_load_template_or_raise(image_path)`：失败时 raise 富信息 `FileNotFoundError`：

   ```
   图片文件不存在: images/web/会中_挂断.png
    ↳ 绝对路径: D:\code\testcase\images\web\会中_挂断.png（项目根 D:\code\testcase）
    ↳ images/ 下相近文件: 会中_挂断按钮.png（相似 0.87）、会中_挂断_new.png（相似 0.85）
   ```

   相近文件用 `difflib.get_close_matches` 扫描 `images/**`，最多 3 条。10 处重复 raise（`base_aw.py:902, 975, 1373, 1397, 1418, 1440, 1466, 1489, 1514, 1538`）全部替换为调用该函数；本地缺失的 `error_type="文件缺失"`。
2. `AWError`（`base_aw.py:30-37`）消息格式不变；`_execute_sync` 的 `full_result` 组装（:561-613）透传 `error_type`（worker 返回的 `ActionResult.to_dict` 已含新字段，自然流入 `log_aw_call` 的 result）。

**报告渲染**（`common/report_generator.py`，三处增强，均向后兼容）：

1. 行级 err-box（:476-484）：`result.error_type` 存在时，在错误文本上方渲染类型徽章（按类型配色：文件缺失=橙、OCR服务/请求错误=红、未找到/相似度/颜色=琥珀、其他=灰）；无 `error_type` 时维持现有平文本。数值已在消息文本里（"最高相似度 0.72，低于阈值 0.90"），无需额外进度条。
2. OCR 内容展示（:539-552 chips 保留）：文本找不到时 `ocr_info` 照常渲染（"屏幕实际识别到: [会议加载中] [取消] …"）；失败且 `ocr_info` 为空时显示"OCR 未识别到任何文字"提示。
3. 目标图片占位（:570-574）：`target_image` 缺失但有 `target_image_path` 时，渲染灰色虚线占位块"目标图片缺失: {path}"（区别于"未匹配到"）。

页首错误框不再加摘要行——worker 文案变富后，现有 traceback 与"首个失败步骤"自动可读。

### 4. 日志补齐（worker / ocr_service）

原则：失败时**一行可 grep 的结构化摘要**（带 request_id、阈值、实际分、原因），不再整包倾倒响应/base64。已打的行不重复加。

**ocr_service（logs/ocr.log，request-id 格式，过滤器只放行 [REQUEST]/[RESPONSE]/[OCR_RAW]/[MATCH] 标签与 ERROR 级）**：

| 位置 | 现状 | 补齐 |
|---|---|---|
| `server.py:106-125` [RESPONSE] 记录键 | 只挑 status/texts/coords/duration_ms/error/text/matches | 键列表加 `ocr_info`（列表显示 `[N items]`，即识别条数）与 3 个新诊断字段（`not_found_reason`/`best_confidence`/`nearest_distance`） |
| `image_matcher.py:199-201` 单目标未命中行 | 已有 `gray fail: 0.xxxx < thr=` | 无需改 |
| `image_matcher.py:325-330, 426-441` match_all / feature 未命中 | 分数只在过程日志，收尾行不带原因 | 收尾行统一带 `reason + best + threshold` |
| `routes.py:236-243` 文本未命中 | info 行（确认现状） | 带上 `filter_text` 与识别条数（取 ocr_info 长度），缺则补 |

**worker（logs/worker.log）**：

| 位置 | 现状 | 补齐 |
|---|---|---|
| `worker/actions/base.py:331-335, 371-380` | 失败时把整个 `ocr_response` 字典倾倒进一行 warning | 替换为一行结构化摘要：复用 `format_find_failure` 的消息 + `request_id`（与报告文案同源），不再 dump 原始响应 |
| `common/ocr_client.py:504` 最终失败行 | 只有 url + 异常字符串 | 补 `http_status`（重试行 :500 同步带上第几次/状态码） |
| `worker/worker.py:1305` Task failed 行 | log_dict 来自 `TaskResult.to_dict` | 无需单独改——`error_type` 字段加入模型后自动出现在该行 |
| `worker/server.py:386-400` 响应日志 | 只脱敏 `screenshot` | `region_screenshot` 纳入脱敏（即 §2 第 6 条） |

### 报告效果示意

图像匹配失败：

```
▶ 第 3 步  image_click("会中_挂断.png")   ❌ 失败  1.2s
   ┌──────────────────────────────────────────────────────┐
   │ 🏷️ 相似度不足                                        │
   │ 未找到目标图片"会中_挂断.png"：最高相似度 0.72，       │
   │ 低于阈值 0.90                                        │
   │ OCR 识别结果: [离开会议] [录制] [更多] [邀请]          │
   │ [当前屏幕] [查找区域] [目标图片]                       │
   │ request_id: a1b2c3                                   │
   └──────────────────────────────────────────────────────┘
```

文本未找到：

```
▶ 第 5 步  ocr_wait("主持人将稍后准许您进入")  ❌ 失败 20.1s
   ┌──────────────────────────────────────────────────────┐
   │ 🏷️ 文本未找到                                        │
   │ 20s 内未识别到文本 "主持人将稍后准许您进入"            │
   │ 屏幕实际识别到: [会议加载中] [取消] [更多]             │
   │ [当前屏幕] [request_id: a1b2c3]                       │
   └──────────────────────────────────────────────────────┘
```

本地文件缺失：

```
🏷️ 文件缺失
图片文件不存在: images/web/会中_挂断.png
 ↳ 绝对路径: D:\code\testcase\images\web\会中_挂断.png
 ↳ images/ 下相近文件: 会中_挂断按钮.png（相似 0.87）
```

## 兼容性

- 新 JSON 字段全部可选：旧 worker 忽略 ocr_service 新字段；旧 testcase 忽略 worker 新字段；报告端无 `error_type` 自动回退平文本。
- `error` 字符串字段保留（内容更丰富），无字段改名/删除。
- 行为变化仅 1 处（对旧端无回归，旧端本就按失败处理）：`get_coord_by_text` 引擎错误由 success+空 → status="error"。

## 测试计划

- **ocr_service**（当前错误路径 0 覆盖）：低于阈值 → 断言 `not_found_reason=below_threshold` + `best_confidence`；颜色关失败 → 断言 `color_check_failed`；near_text 三种失败 → 断言对应 reason；data-URI 前缀剥离；引擎错误 → status=error。
- **autotest**：`get_last_failure` 透传单测；`format_find_failure` 消息拼装单测（含数值）；更新断言 `"Image not found"` 固定文案的既有用例；`error_type` 序列化往返测试；base.py 失败摘要行用 caplog 断言（不再含 `ocr_response` 整包）。
- **testcase**：`tests/unit/test_report_generator.py` 回归 + 新增：徽章按类型配色、无 error_type 回退、空 ocr_info 提示、占位块；`_load_template_or_raise` 单测（相近文件提示）。

## 实施顺序

1. ocr_service（源头字段）→ 2. autotest worker（透传 + 文案）→ 3. testcase（渲染）。
每步独立可部署；只做前 1-2 步时报告仍回退平文本，不坏。
