"""HTML 报告生成器（V2）。

设计要点：
- 两级时间线：业务方法分组卡（可折叠）+ 组内原子操作紧凑行。
- 分组依据 parent_call_id（业务方法每次调用的唯一 ID），跨 AW / 同名多次调用不会错位。
- 组标题自动取业务方法 docstring 首行（display_name），新 AW 零登记。
- 参数展示采用黑名单过滤（新参数自动显示），ocr_info 有数据即显示。
- 无归属的原子操作合并为"直接操作"兜底组，不再散落在时间线上。
"""

import html as _html_mod
import json
import re
from typing import Any, Dict, List, Optional


# 不在报告中显示的参数（内部参数或 base64 大数据）
_HIDDEN_ARGS = {
    "user_id", "user_account", "user_name", "user_ip",
    "target_image", "image_base64", "screenshot", "error_screenshot",
    "platform",
}

# 原子操作耗时超过该阈值时高亮显示（毫秒）
_SLOW_MS = 5000


def _esc(text: Any) -> str:
    """HTML 转义（所有用户数据渲染前必须经过）。"""
    return _html_mod.escape(str(text), quote=True)


class HTMLReportGenerator:
    """HTML 报告生成器。"""

    # ── 通用帮手 ─────────────────────────────────────────

    @staticmethod
    def _clean_text_for_display(text: str) -> str:
        """清理文本内容，过滤 base64 数据。"""
        if not text:
            return ""
        # PNG base64 特征：iVBORw0KGgo 开头的长字符串
        return re.sub(r'iVBORw0KGgo[A-Za-z0-9+/=]{100,}', '[截图数据]', text)

    @staticmethod
    def _clean_response_for_display(response: Dict[str, Any]) -> Dict[str, Any]:
        """清理响应数据，移除大型 base64 数据用于显示。"""
        if not isinstance(response, dict):
            return response
        cleaned = {}
        for key, value in response.items():
            if key == "screenshots":
                count = len(value) if isinstance(value, list) else 0
                if count > 0:
                    cleaned[key] = f"[{count}张截图]"
            elif key in ("error_screenshot", "screenshot") and isinstance(value, str) and len(value) > 100:
                cleaned[key] = "[截图数据]"
            elif key == "ocr_info":
                continue  # OCR 结果单独渲染为 chips
            elif key == "actions" and isinstance(value, list):
                cleaned[key] = []
                for action in value:
                    if isinstance(action, dict):
                        clean_action = {}
                        for ak, av in action.items():
                            if ak in ("screenshot", "error_screenshot") and isinstance(av, str) and len(av) > 100:
                                clean_action[ak] = "[截图数据]"
                            elif ak == "output" and isinstance(av, str) and len(av) > 500:
                                clean_action[ak] = "[输出数据]"
                            else:
                                clean_action[ak] = av
                        cleaned[key].append(clean_action)
                    else:
                        cleaned[key].append(action)
            else:
                cleaned[key] = value
        return cleaned

    @staticmethod
    def _format_duration(duration_ms: int) -> str:
        """格式化耗时，超过 1 秒显示为秒。"""
        if duration_ms >= 1000:
            return f"{duration_ms / 1000:.1f}s"
        return f"{duration_ms}ms"

    @staticmethod
    def _format_total_duration(duration_ms: int) -> str:
        """格式化总耗时，超过 1 分钟显示为 "Xm Ys"。"""
        if duration_ms >= 60000:
            minutes = duration_ms // 60000
            seconds = (duration_ms % 60000) / 1000
            return f"{minutes}m {seconds:.0f}s"
        return HTMLReportGenerator._format_duration(duration_ms)

    @staticmethod
    def _get_user_color(user_id: str) -> str:
        """根据用户 ID 返回标签颜色。"""
        colors = {
            "userA": "#3b82f6",  # 蓝色
            "userB": "#22c55e",  # 绿色
            "userC": "#8b5cf6",  # 紫色
            "userD": "#f59e0b",  # 黄色
        }
        base_user_id = user_id.replace("_api", "")
        return colors.get(base_user_id, "#6b7280")  # 默认灰色

    @staticmethod
    def _format_platform(platform: str) -> str:
        """把设备类型转换为报告中的友好名称。"""
        labels = {
            "windows": "Windows",
            "web": "Web",
            "mac": "macOS",
            "ios": "iOS",
            "android": "Android",
            "harmony_pc": "Harmony PC",
            "harmony_mobile": "Harmony Mobile",
            "api": "API",
        }
        value = str(platform or "").strip()
        return labels.get(value.lower(), value or "未知设备")

    @staticmethod
    def _format_value_for_display(value: Any, max_len: int = 5000) -> str:
        """将请求或响应值格式化为便于阅读的文本。"""
        if isinstance(value, (dict, list, tuple)):
            try:
                text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
            except (TypeError, ValueError):
                text = str(value)
        else:
            text = str(value)

        if len(text) > max_len:
            return text[:max_len] + "\n...[内容已截断]"
        return text

    @staticmethod
    def _parse_json_value(value: Any) -> Any:
        """尽量把 HTTP 响应体中的 JSON 字符串解析为结构化数据。"""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _format_args_inline(args: Dict[str, Any], max_len: int = 90) -> str:
        """格式化原子操作参数为单行字符串（黑名单过滤，新参数自动显示）。"""
        parts = []
        for k, v in args.items():
            if k in _HIDDEN_ARGS or v is None:
                continue
            if isinstance(v, str):
                if len(v) > 40:
                    v = v[:37] + "..."
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")
        text = ", ".join(parts)
        if len(text) > max_len:
            text = text[:max_len - 3] + "..."
        return text

    # ── 分组算法 ─────────────────────────────────────────

    @staticmethod
    def _build_timeline(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把日志流构建为有序时间线条目。

        条目类型：
        - {"kind": "phase", "log": ...}          阶段分隔条（step 日志）
        - {"kind": "error", "log": ...}          错误条目
        - {"kind": "group", ...}                 业务方法分组

        分组规则：
        1. 原子操作按 parent_call_id 精确归组（首次出现的位置决定组顺序）。
        2. 业务方法日志（is_business_method）按 call_id 关联为组头；
           parallel 模式成功时无组头日志，用子操作的 parent_display 合成标题。
        3. 兼容旧数据：无 parent_call_id 但有 parent_aw 时按 parent_aw 归组。
        4. 无任何父级的原子操作合并进连续的"直接操作"兜底组。
        """
        timeline: List[Dict[str, Any]] = []
        groups_by_key: Dict[str, Dict[str, Any]] = {}
        orphan_group: Optional[Dict[str, Any]] = None

        def _new_group(key: str) -> Dict[str, Any]:
            group = {
                "kind": "group", "key": key, "title": "", "method_label": "",
                "rows": [], "biz_log": None, "nested": False, "orphan": False,
                "children": [],
            }
            timeline.append(group)
            if key:
                groups_by_key[key] = group
            return group

        for log in logs:
            log_type = log.get("type", "")

            if log_type == "step":
                step_name = log.get("step", "")
                # hook 日志在 aw_call 中已有对应操作，跳过避免重复
                if step_name.startswith("执行 hook:"):
                    continue
                timeline.append({"kind": "phase", "log": log})
                orphan_group = None
                continue

            if log_type == "error":
                timeline.append({"kind": "error", "log": log})
                orphan_group = None
                continue

            if log_type == "aw_log":
                # AW 自定义日志和原子操作一样，按父级业务方法归组。
                pid = log.get("parent_call_id", "")
                if not pid and log.get("parent_aw"):
                    pid = f"legacy::{log['parent_aw']}"
                if pid:
                    group = groups_by_key.get(pid)
                    if group is None:
                        group = _new_group(pid)
                    group["rows"].append(log)
                    orphan_group = None
                else:
                    if orphan_group is None:
                        orphan_group = _new_group("")
                        orphan_group["orphan"] = True
                    orphan_group["rows"].append(log)
                continue

            if log_type != "aw_call":
                continue  # worker_call / screenshot 不进时间线

            if log.get("is_business_method"):
                cid = log.get("call_id", "")
                group = groups_by_key.get(cid) if cid else None
                if group is None:
                    group = _new_group(cid)
                group["biz_log"] = log
                if log.get("parent_call_id"):
                    group["nested"] = True  # 嵌套业务方法（外层组的子步骤）
                orphan_group = None
                continue

            # 原子操作：确定归属键
            pid = log.get("parent_call_id", "")
            if not pid and log.get("parent_aw"):
                pid = f"legacy::{log['parent_aw']}"  # 兼容旧数据
            if pid:
                group = groups_by_key.get(pid)
                if group is None:
                    group = _new_group(pid)
                group["rows"].append(log)
                orphan_group = None
            else:
                # 孤儿操作：合并进连续的"直接操作"组
                if orphan_group is None:
                    orphan_group = _new_group("")
                    orphan_group["orphan"] = True
                orphan_group["rows"].append(log)

        # 嵌套业务方法归入父组：一个 AW 调用其它 AW 时聚合为父卡片内的子卡片，
        # 不再平铺为顶层卡片
        nested_groups = []
        for entry in timeline:
            if entry["kind"] != "group":
                continue
            biz_log = entry.get("biz_log")
            pcid = biz_log.get("parent_call_id", "") if biz_log else ""
            parent = groups_by_key.get(pcid) if pcid else None
            if parent is not None and parent is not entry:
                parent["children"].append(entry)
                entry["nested"] = True
                nested_groups.append(entry)
        if nested_groups:
            nested_ids = {id(g) for g in nested_groups}
            timeline = [e for e in timeline if id(e) not in nested_ids]

        # 补全每组的标题 / 统计信息（含嵌套子组），再自底向上聚合
        for entry in timeline:
            if entry["kind"] != "group":
                continue
            for group in HTMLReportGenerator._iter_group_tree(entry):
                HTMLReportGenerator._finalize_group(group)
            HTMLReportGenerator._aggregate_group(entry)

        return timeline

    @staticmethod
    def _iter_group_tree(group: Dict[str, Any]):
        """深度优先遍历分组及其全部嵌套子组。"""
        yield group
        for child in group["children"]:
            yield from HTMLReportGenerator._iter_group_tree(child)

    @staticmethod
    def _aggregate_group(group: Dict[str, Any]) -> None:
        """自底向上聚合嵌套子组的统计（总步数 / 失败数 / 状态）。"""
        total = len(group["rows"])
        fails = group["fail_rows"]
        ok = group["ok"]
        for child in group["children"]:
            HTMLReportGenerator._aggregate_group(child)
            total += child["total_rows"]
            fails += child["fail_total"]
            ok = ok and child["ok"]
        group["total_rows"] = total
        group["fail_total"] = fails
        group["ok"] = ok

    @staticmethod
    def _finalize_group(group: Dict[str, Any]) -> None:
        """补全分组的标题、用户、状态、耗时等信息。"""
        biz_log = group["biz_log"]
        rows = group["rows"]
        first_row = rows[0] if rows else None

        if group["orphan"]:
            group["title"] = "直接操作"
            group["method_label"] = ""
        elif biz_log:
            aw_name = biz_log.get("aw_name", "")
            method = biz_log.get("method", "")
            group["title"] = biz_log.get("display_name") or method
            group["method_label"] = f"{aw_name}.{method}"
        elif first_row:
            # parallel 成功场景无组头日志：用子操作携带的父级信息合成
            parent_aw = first_row.get("parent_aw", "")
            group["title"] = first_row.get("parent_display") or parent_aw.split(".")[-1] or "业务步骤"
            group["method_label"] = parent_aw
        else:
            group["title"] = "业务步骤"

        # 用户信息：优先组头日志，其次首个子操作
        src = biz_log or first_row or {}
        args = src.get("args", {})
        group["user_id"] = args.get("user_id", "")
        group["user_name"] = args.get("user_name", "")
        group["user_ip"] = args.get("user_ip", "")
        group["user_platform"] = args.get("user_platform", "")

        # 状态：组头失败 或 任一子操作失败 视为失败
        biz_ok = biz_log.get("success", True) if biz_log else True
        group["fail_rows"] = sum(1 for r in rows if not r.get("success", True))
        group["ok"] = biz_ok and group["fail_rows"] == 0

        # 耗时：优先组头记录，否则累加子操作
        if biz_log and biz_log.get("duration_ms"):
            group["duration_ms"] = biz_log["duration_ms"]
        else:
            group["duration_ms"] = sum(r.get("duration_ms", 0) for r in rows)

        # 时间：组内最早的日志时间
        times = [r.get("time", "") for r in rows if r.get("time")]
        if biz_log and biz_log.get("time"):
            times.append(biz_log["time"])
        group["time"] = min(times) if times else ""

        # 组头日志需要作为行渲染的两种情况：
        # 1) 业务方法自身失败但无失败子操作（如方法体断言失败）
        # 2) 组内无任何子内容（如业务方法只做了直连 HTTP 调用），
        #    渲染组头行以展示参数与耗时，避免"无原子操作记录"空卡
        if biz_log:
            has_biz_row = any(r is biz_log for r in rows)
            if not has_biz_row and (
                (not biz_ok) or (not rows and not group.get("children"))
            ):
                rows.append(biz_log)
                if not biz_ok:
                    group["fail_rows"] += 1

    # ── 渲染 ─────────────────────────────────────────────

    @staticmethod
    def _render_row(log: Dict[str, Any]) -> str:
        """渲染组内单条原子操作（紧凑行 + 可展开详情）。"""
        if log.get("type") == "aw_log":
            message = log.get("message", "")
            row_html = (
                '<div class="row aw-log" onclick="td(this)">'
                '<span class="log-dot">●</span>'
                f'<span class="r-time">{_esc(log.get("time", ""))}</span>'
                '<span class="r-method">日志</span>'
                f'<span class="r-args">{_esc(message)}</span>'
                '</div>'
            )
            detail_html = (
                '<div class="row-detail log-detail">'
                '<div class="k">AW 日志</div>'
                f'<div class="v">{_esc(message)}</div>'
                '</div>'
            )
            return row_html + detail_html

        success = log.get("success", True)
        method = log.get("method", "")
        args = log.get("args", {})
        result = log.get("result", {})
        duration = log.get("duration_ms", 0)
        time_str = log.get("time", "")

        # 业务方法日志作为行渲染时显示 display_name
        if log.get("is_business_method") and log.get("display_name"):
            args_text = log["display_name"]
        else:
            args_text = HTMLReportGenerator._format_args_inline(args)

        # 截图标记
        error_screenshot = result.get("error_screenshot", "") if isinstance(result, dict) else ""
        target_image = log.get("target_image", "")
        shot_count = sum(1 for s in (error_screenshot, target_image) if s and len(s) > 100)
        shot_html = f'<span class="r-shot">📷 {shot_count}</span>' if shot_count else ""

        row_classes = ["row"]
        if not success:
            row_classes.append("fail")
        if duration >= _SLOW_MS:
            row_classes.append("slow")

        row_html = (
            f'<div class="{" ".join(row_classes)}" onclick="td(this)">'
            f'<span class="dot"></span>'
            f'<span class="r-time">{_esc(time_str)}</span>'
            f'<span class="r-method">{_esc(method)}</span>'
            f'<span class="r-args">{_esc(args_text)}</span>'
            f'{shot_html}'
            f'<span class="r-dur">{HTMLReportGenerator._format_duration(duration)}</span>'
            f'</div>'
        )
        detail_html = HTMLReportGenerator._render_row_detail(log)
        return row_html + detail_html

    @staticmethod
    def _render_row_detail(log: Dict[str, Any]) -> str:
        """渲染原子操作的展开详情（错误 / 请求响应 / OCR / 截图）。"""
        success = log.get("success", True)
        args = log.get("args", {})
        result = log.get("result", {}) if isinstance(log.get("result"), dict) else {}
        request_id = log.get("request_id", "")

        parts = []

        # 错误信息
        if not success:
            error_msg = result.get("error", "")
            if error_msg:
                clean_err = HTMLReportGenerator._clean_text_for_display(str(error_msg))
                rid = f'<div class="rid">request_id: {_esc(request_id)}</div>' if request_id else ""
                parts.append(
                    f'<div class="err-box"><div class="k">错误信息</div>'
                    f'<div class="v">{_esc(clean_err)}</div>{rid}</div>'
                )
        elif request_id:
            parts.append(f'<div class="rid">request_id: {_esc(request_id)}</div>')

        # HTTP 请求 / 响应使用专门布局，避免响应体被压成不可读的 Python 字典。
        clean_args = {k: v for k, v in args.items() if k not in _HIDDEN_ARGS}
        clean_result = HTMLReportGenerator._clean_response_for_display(result)
        kv_parts = []
        is_http = "status_code" in result and ("url" in args or "method" in args)
        if is_http:
            request_parts = {
                key: value for key, value in clean_args.items()
                if key in {"method", "url", "params", "body"}
            }
            if request_parts:
                request_text = HTMLReportGenerator._format_value_for_display(request_parts)
                kv_parts.append(f'<div><div class="k">HTTP 请求</div><pre class="v code-block">{_esc(request_text)}</pre></div>')

            status_code = result.get("status_code", "-")
            try:
                status_class = "http-ok" if 200 <= int(status_code) < 400 else "http-fail"
            except (TypeError, ValueError):
                status_class = "http-fail"
            body = HTMLReportGenerator._parse_json_value(result.get("body", ""))
            body_text = HTMLReportGenerator._format_value_for_display(body)
            response_html = (
                '<div><div class="k">HTTP 响应</div>'
                f'<div class="http-status {status_class}">状态码 {_esc(status_code)}</div>'
                f'<pre class="v code-block http-body">{_esc(body_text or "（空响应体）")}</pre></div>'
            )
            kv_parts.append(response_html)
        else:
            if clean_args:
                request_text = HTMLReportGenerator._format_value_for_display(clean_args)
                kv_parts.append(f'<div><div class="k">请求</div><pre class="v code-block">{_esc(request_text)}</pre></div>')
            if clean_result:
                result_text = HTMLReportGenerator._format_value_for_display(clean_result)
                kv_parts.append(f'<div><div class="k">响应</div><pre class="v code-block">{_esc(result_text)}</pre></div>')
        if kv_parts:
            parts.append(f'<div class="kv">{"".join(kv_parts)}</div>')

        # OCR 识别结果：有数据即显示（不再按方法名白名单门控）
        ocr_info = result.get("ocr_info", [])
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
                parts.append(f'<div class="ocr-box"><div class="k">OCR 识别结果</div><div>{"".join(chips)}</div></div>')

        # 截图（失败时）
        if not success:
            shots = []
            error_screenshot = result.get("error_screenshot", "")
            target_image = log.get("target_image", "")
            if error_screenshot and len(error_screenshot) > 100:
                shots.append(
                    f'<div class="shot" onclick="showImage(this.querySelector(\'img\').src);event.stopPropagation()">'
                    f'<img src="data:image/png;base64,{error_screenshot}"><span class="cap">当前屏幕</span></div>'
                )
            if target_image and len(target_image) > 100:
                shots.append(
                    f'<div class="shot" onclick="showImage(this.querySelector(\'img\').src);event.stopPropagation()">'
                    f'<img src="data:image/png;base64,{target_image}"><span class="cap">目标图片</span></div>'
                )
            if shots:
                parts.append(f'<div class="shots">{"".join(shots)}</div>')

        if not parts:
            return ""
        open_class = " open" if not success else ""
        return f'<div class="row-detail{open_class}">{"".join(parts)}</div>'

    @staticmethod
    def _render_group(
        group: Dict[str, Any],
        anchor_id: str,
        depth: int = 0,
        user_details: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """渲染业务方法分组卡（嵌套调用的子 AW 递归渲染为子卡片）。"""
        ok = group["ok"]
        rows = group["rows"]
        children = group.get("children", [])
        user_id = group.get("user_id", "")
        user_color = HTMLReportGenerator._get_user_color(user_id)
        detail = (user_details or {}).get(user_id, {})
        is_api_user = bool(detail.get("is_api") or user_id.endswith("_api"))
        platform = "" if is_api_user else (
            group.get("user_platform")
            or detail.get("display_platform")
            or detail.get("platform")
        )

        state_class = "ok" if ok else "failed open"
        if depth:
            state_class += " sub"
        icon = "✓" if ok else "✗"
        title_style = "" if ok else ' style="color:var(--red)"'

        user_label = user_id
        if platform and user_id:
            user_label = f"{user_id} · {HTMLReportGenerator._format_platform(platform)}"
        user_tag = (
            f'<span class="u-tag" style="background:{user_color}">{_esc(user_label)}</span>'
            if user_id else ""
        )
        method_label = (
            f'<span class="g-method">{_esc(group["method_label"])}</span>'
            if group.get("method_label") else ""
        )

        # 统计与进度小条（含嵌套子组聚合值）
        total = group.get("total_rows", len(rows))
        fails = group.get("fail_total", group["fail_rows"])
        cnt_html = f'<b>{total}</b> 步'
        if fails:
            cnt_html += f' · <span class="f">{fails} 失败</span>'
        ok_pct = int((total - fails) / total * 100) if total else 100
        bar_html = f'<span class="g-bar"><i style="width:{ok_pct}%"></i>'
        if fails:
            bar_html += f'<i class="f" style="width:{100 - ok_pct}%"></i>'
        bar_html += '</span>'

        # 组内内容：自身原子操作行与嵌套子卡片按时间交错排序
        items = [("row", r.get("time", ""), r) for r in rows]
        items += [("group", c.get("time", ""), c) for c in children]
        items.sort(key=lambda it: it[1])
        parts = []
        for kind, _t, obj in items:
            if kind == "row":
                parts.append(HTMLReportGenerator._render_row(obj))
            else:
                parts.append(HTMLReportGenerator._render_group(obj, "", depth + 1, user_details))
        rows_html = "".join(parts)
        if not rows_html:
            rows_html = '<div class="row-empty">无原子操作记录</div>'

        anchor_attr = f' id="{anchor_id}"' if anchor_id else ""
        return f'''
    <div class="group {state_class}"{anchor_attr} data-user="{_esc(user_id)}">
        <div class="group-header" onclick="tg(this)">
            <span class="chevron">▶</span>
            <span class="g-icon">{icon}</span>
            {user_tag}
            <span class="g-title"{title_style}>{_esc(group["title"])}</span>
            {method_label}
            <div class="g-meta">
                <span class="cnt">{cnt_html}</span>
                {bar_html}
                <span class="g-dur">{HTMLReportGenerator._format_duration(group["duration_ms"])}</span>
            </div>
        </div>
        <div class="rows">{rows_html}</div>
    </div>'''

    @staticmethod
    def _render_phase(log: Dict[str, Any]) -> str:
        """渲染阶段分隔条（step 类型日志），有详情时可点击展开。"""
        step_name = log.get("step", "")
        time_str = log.get("time", "")
        detail = log.get("detail", "")
        clean_detail = HTMLReportGenerator._clean_text_for_display(detail) if detail else ""

        if clean_detail:
            return f'''
    <div class="phase-wrap">
        <div class="phase clickable" onclick="tp(this)"><span class="t">{_esc(time_str)}</span> {_esc(step_name)} <span class="phase-more">详情 ▾</span></div>
        <pre class="phase-detail">{_esc(clean_detail)}</pre>
    </div>'''
        return f'<div class="phase"><span class="t">{_esc(time_str)}</span> {_esc(step_name)}</div>'

    @staticmethod
    def _render_error(log: Dict[str, Any]) -> str:
        """渲染 error 类型日志。"""
        time_str = log.get("time", "")
        error = HTMLReportGenerator._clean_text_for_display(log.get("error", ""))
        return f'''
    <div class="error-entry"><span class="t">{_esc(time_str)}</span> ⚠ {_esc(error)}</div>'''

    @staticmethod
    def _build_screenshots_html(logs: List[Dict[str, Any]], is_api_failure: bool = False) -> str:
        """构建末尾截图区 HTML（只显示步骤中没有截图的用户，避免重复）。"""
        screenshots = [log for log in logs if log.get("type") == "screenshot"]
        if not screenshots:
            return ""

        users_with_step_screenshot = set()
        for log in logs:
            if log.get("type") != "aw_call":
                continue
            result = log.get("result", {})
            if not isinstance(result, dict):
                continue
            has_screenshot = bool(result.get("error_screenshot", "")) and len(result.get("error_screenshot", "")) > 100
            if not has_screenshot:
                for action in result.get("actions", []) or []:
                    if isinstance(action, dict) and len(action.get("screenshot", "") or "") > 100:
                        has_screenshot = True
                        break
            if has_screenshot:
                user_id = log.get("args", {}).get("user_id", "")
                if user_id:
                    users_with_step_screenshot.add(user_id)

        filtered = [s for s in screenshots if s.get("user_id", "") not in users_with_step_screenshot]
        if not filtered:
            return ""

        items = []
        for shot in filtered:
            base64_data = shot.get("base64", "")
            user_id = shot.get("user_id", "")
            items.append(
                f'<div class="shot" onclick="showImage(this.querySelector(\'img\').src)">'
                f'<img src="data:image/png;base64,{base64_data}" alt="{_esc(user_id)}">'
                f'<span class="cap">📷 {_esc(user_id)}</span></div>'
            )

        title = "📸 用户截图" if is_api_failure else "📸 其他用户截图"
        return f'''
    <div class="screenshots-card">
        <div class="sc-title">{title}</div>
        <div class="shots">{"".join(items)}</div>
    </div>'''

    @staticmethod
    def _collect_user_details(
        logs: List[Dict[str, Any]],
        user_details: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """合并资源申请信息和 AW 日志中的用户信息。"""
        collected: Dict[str, Dict[str, Any]] = {}
        for user_id, detail in (user_details or {}).items():
            collected[user_id] = dict(detail or {})

        # 先读取资源申请阶段的原始响应，兼容 data/resources 或直接字典结构。
        for log in logs:
            if log.get("type") != "step" or log.get("step") != "申请用户资源":
                continue
            detail = log.get("detail", "")
            try:
                payload = json.loads(detail) if isinstance(detail, str) else detail
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            resources = payload.get("data") or payload.get("resources") or payload
            if not isinstance(resources, dict):
                continue
            for user_id, resource in resources.items():
                if not isinstance(resource, dict):
                    continue
                current = collected.setdefault(user_id, {})
                for key, value in resource.items():
                    if value not in (None, "") and key not in current:
                        current[key] = value
                if resource.get("device_type") and not current.get("platform"):
                    current["platform"] = resource["device_type"]

        # AW 日志作为最后一层兜底，确保不经过 conftest 直接生成的报告也能展示用户。
        for log in logs:
            if log.get("type") not in {"aw_call", "aw_log"}:
                continue
            args = log.get("args", {})
            user_id = args.get("user_id", "")
            if not user_id:
                continue
            current = collected.setdefault(user_id, {})
            for key, value in {
                "name": args.get("user_name", ""),
                "ip": args.get("user_ip", ""),
                "platform": args.get("user_platform", "") or args.get("platform", ""),
            }.items():
                if value not in (None, "") and not current.get(key):
                    current[key] = value

        return collected

    @staticmethod
    def _build_resource_summary_html(
        user_details: Dict[str, Dict[str, Any]],
    ) -> str:
        """构建可换行的用户资源卡片区，避免用户过多时挤压头部。"""
        resource_users = [
            (user_id, detail)
            for user_id, detail in user_details.items()
            if not user_id.endswith("_api")
        ]
        if not resource_users:
            return ""

        cards = []
        for user_id, detail in resource_users:
            platform = detail.get("display_platform") or detail.get("device_type") or detail.get("platform", "")
            meta = " · ".join(
                str(value) for value in (detail.get("name", ""), detail.get("ip", ""))
                if value
            )
            meta_html = f'<div class="resource-meta">{_esc(meta or "资源信息未返回")}</div>'
            cards.append(
                f'<div class="resource-card" data-user="{_esc(user_id)}">'
                f'<div class="resource-card-top"><span class="dot" style="background:{HTMLReportGenerator._get_user_color(user_id)}"></span>'
                f'<strong>{_esc(user_id)}</strong>'
                f'<span class="platform-badge">{_esc(HTMLReportGenerator._format_platform(platform))}</span></div>'
                f'{meta_html}</div>'
            )

        return (
            '<div class="resource-summary">'
            f'<div class="resource-summary-title">申请资源 <span>{len(resource_users)} 位用户</span></div>'
            f'<div class="resource-grid">{"".join(cards)}</div>'
            '</div>'
        )

    # ── 主入口 ───────────────────────────────────────────

    @staticmethod
    def generate(
        report_path,
        case_name: str,
        case_title: str = "",
        logs: List[Dict[str, Any]] = [],
        duration_ms: int = 0,
        status: str = "passed",
        error_msg: str = "",
        is_api_failure: bool = False,
        user_details: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """生成 HTML 报告。"""
        timeline = HTMLReportGenerator._build_timeline(logs)
        groups = [e for e in timeline if e["kind"] == "group"]

        # ── 统计（含嵌套子组聚合值） ──
        ops_total = sum(g.get("total_rows", len(g["rows"])) for g in groups)
        ops_fail = sum(g.get("fail_total", g["fail_rows"]) for g in groups)
        ops_ok = ops_total - ops_fail
        first_failed = next((g for g in groups if not g["ok"]), None)
        passed = status == "passed"

        # 用户信息保持资源申请和日志中的首次出现顺序。
        users = HTMLReportGenerator._collect_user_details(logs, user_details)

        # ── 时间线 HTML（同时给分组编锚点） ──
        timeline_parts = []
        anchor_index = 0
        progress_parts = []
        for entry in timeline:
            if entry["kind"] == "group":
                anchor_index += 1
                anchor_id = f"g{anchor_index}"
                timeline_parts.append(HTMLReportGenerator._render_group(entry, anchor_id, user_details=users))
                cls = "" if entry["ok"] else ' class="fail"'
                tip = _esc(entry["title"]) + ("" if entry["ok"] else " — 失败")
                progress_parts.append(f'<a href="#{anchor_id}"{cls} title="{tip}"></a>')
            elif entry["kind"] == "phase":
                timeline_parts.append(HTMLReportGenerator._render_phase(entry["log"]))
            elif entry["kind"] == "error":
                timeline_parts.append(HTMLReportGenerator._render_error(entry["log"]))
        timeline_html = "\n".join(timeline_parts) or '<div class="empty-logs">暂无执行步骤</div>'
        progress_html = f'<div class="progress-track">{"".join(progress_parts)}</div>' if progress_parts else ""

        # ── 头部 ──
        badge = ('<span class="badge-status passed">✓ 通过</span>' if passed
                 else '<span class="badge-status failed">✗ 失败</span>')
        subtitle = f'<div class="subtitle">{_esc(case_title.strip())}</div>' if case_title.strip() else ""

        first_failed_html = ""
        if first_failed:
            label = first_failed.get("method_label") or first_failed["title"]
            first_failed_html = (
                '<div class="stat-sep"></div>'
                f'<div class="stat"><span class="num small red">{_esc(label)}</span>'
                '<span class="lbl">首个失败步骤</span></div>'
            )

        resource_summary_html = HTMLReportGenerator._build_resource_summary_html(users)

        error_box = ""
        if error_msg:
            clean_error = HTMLReportGenerator._clean_text_for_display(error_msg)
            error_box = f'<div class="error-box">{_esc(clean_error)}</div>'

        # 用户过滤按钮
        user_btns = "".join(
            f'<button class="tbtn ubtn" onclick="filterUser(this,\'{_esc(uid)}\')">{_esc(uid)}</button>'
            for uid in users
        )

        screenshots_html = HTMLReportGenerator._build_screenshots_html(logs, is_api_failure)

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(case_name)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">

    <div class="header {'passed' if passed else ''}">
        <div class="header-top">
            <div>
                <h1>{_esc(case_name)}</h1>
                {subtitle}
            </div>
            {badge}
        </div>
        <div class="stat-row">
            <div class="stat"><span class="num">{HTMLReportGenerator._format_total_duration(duration_ms)}</span><span class="lbl">总耗时</span></div>
            <div class="stat-sep"></div>
            <div class="stat"><span class="num">{len(groups)}</span><span class="lbl">业务步骤</span></div>
            <div class="stat"><span class="num green">{ops_ok}</span><span class="lbl">操作成功</span></div>
            <div class="stat"><span class="num red">{ops_fail}</span><span class="lbl">操作失败</span></div>
            {first_failed_html}
        </div>
        {resource_summary_html}
        {progress_html}
        {error_box}
    </div>

    <div class="toolbar">
        <button class="tbtn fail-filter" onclick="document.body.classList.toggle('only-fail');this.classList.toggle('active')">只看失败</button>
        <button class="tbtn" onclick="toggleAll(true)">全部展开</button>
        <button class="tbtn" onclick="toggleAll(false)">全部收起</button>
        <span class="vsep"></span>
        <button class="tbtn ubtn active" onclick="filterUser(this,'')">全部用户</button>
        {user_btns}
        <span class="spacer"></span>
        <span class="hint">{len(groups)} 个业务步骤 · {ops_total} 次原子操作{' · 失败步骤已自动展开' if ops_fail or not passed else ''}</span>
    </div>

    <div class="timeline">
{timeline_html}
    </div>
    {screenshots_html}
</div>

<div class="modal" id="modal"><img id="modal-img" src=""></div>

<script>{_JS}</script>
</body>
</html>'''

        report_path.write_text(html, encoding="utf-8")


# ── 样式（普通字符串，避免 f-string 花括号转义） ──────────
_CSS = """
* { box-sizing: border-box; margin: 0; }
:root {
    --green: #16a34a; --green-bg: #f0fdf4; --green-soft: #dcfce7;
    --red: #dc2626; --red-bg: #fef2f2; --red-soft: #fee2e2;
    --blue: #3b82f6; --ink: #0f172a; --ink-2: #475569; --ink-3: #94a3b8;
    --line: #e2e8f0; --bg: #f1f5f9;
    --mono: 'Cascadia Code', Consolas, monospace;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
    background: var(--bg); color: var(--ink); padding: 20px 16px;
}
.container { max-width: 1280px; margin: 0 auto; }

/* ── 头部 ── */
.header {
    background: white; border-radius: 14px; padding: 20px 24px 16px;
    border: 1px solid var(--line); border-top: 4px solid var(--red);
    box-shadow: 0 1px 3px rgba(15,23,42,.06); margin-bottom: 14px;
}
.header.passed { border-top-color: var(--green); }
.header-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.header h1 { font-size: 19px; font-weight: 700; letter-spacing: -.2px; }
.header .subtitle { font-size: 13px; color: var(--ink-2); margin-top: 4px; white-space: pre-line; }
.badge-status {
    display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px;
    border-radius: 999px; font-weight: 700; font-size: 14px; flex-shrink: 0;
}
.badge-status.failed { background: var(--red-soft); color: var(--red); }
.badge-status.passed { background: var(--green-soft); color: var(--green); }
.stat-row { display: flex; gap: 24px; margin-top: 16px; flex-wrap: wrap; align-items: center; }
.stat { display: flex; flex-direction: column; gap: 2px; }
.stat .num { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }
.stat .num.small { font-size: 13px; padding-top: 6px; font-family: var(--mono); }
.stat .num.red { color: var(--red); } .stat .num.green { color: var(--green); }
.stat .lbl { font-size: 11px; color: var(--ink-3); }
.stat-sep { width: 1px; height: 30px; background: var(--line); }
.user-chips { display: flex; gap: 6px; margin-left: auto; flex-wrap: wrap; }
.user-chip {
    display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
    padding: 4px 10px; border-radius: 999px; background: #f8fafc; border: 1px solid var(--line);
    color: var(--ink-2);
}
.user-chip .dot { width: 8px; height: 8px; border-radius: 50%; }
.resource-summary {
    margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line);
}
.resource-summary-title {
    display: flex; align-items: baseline; gap: 8px;
    font-size: 12px; font-weight: 700; color: var(--ink-2); margin-bottom: 8px;
}
.resource-summary-title span { font-size: 11px; color: var(--ink-3); font-weight: 400; }
.resource-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px;
}
.resource-card {
    min-width: 0; padding: 8px 10px; border: 1px solid var(--line);
    border-radius: 9px; background: #f8fafc;
}
.resource-card-top { display: flex; align-items: center; gap: 6px; min-width: 0; }
.resource-card-top .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.resource-card-top strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.platform-badge {
    margin-left: auto; flex-shrink: 0; padding: 2px 6px; border-radius: 5px;
    background: #e0e7ff; color: #3730a3; font-size: 10.5px; font-weight: 700;
}
.resource-meta {
    margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    color: var(--ink-3); font-size: 11px;
}
.progress-track { display: flex; gap: 3px; margin-top: 14px; height: 8px; }
.progress-track a { flex: 1; border-radius: 3px; background: var(--green); opacity: .75; transition: .15s; }
.progress-track a:hover { opacity: 1; transform: scaleY(1.5); }
.progress-track a.fail { background: var(--red); opacity: 1; }
.error-box {
    margin-top: 14px; padding: 10px 14px; background: var(--red-bg);
    border: 1px solid #fca5a5; border-radius: 10px;
    font-family: var(--mono); font-size: 12px; color: var(--red);
    white-space: pre-wrap; word-break: break-all; max-height: 180px; overflow: auto;
}

/* ── 工具栏 ── */
.toolbar {
    position: sticky; top: 8px; z-index: 10;
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    background: rgba(255,255,255,.92); backdrop-filter: blur(8px);
    border: 1px solid var(--line); border-radius: 12px;
    padding: 8px 12px; margin-bottom: 14px; box-shadow: 0 1px 4px rgba(15,23,42,.05);
}
.tbtn {
    border: 1px solid var(--line); background: white; border-radius: 8px;
    padding: 5px 12px; font-size: 12.5px; color: var(--ink-2); cursor: pointer; transition: .15s;
}
.tbtn:hover { border-color: #94a3b8; color: var(--ink); }
.tbtn.active { background: var(--ink); color: white; border-color: var(--ink); }
.tbtn.fail-filter.active { background: var(--red); border-color: var(--red); }
.toolbar .vsep { width: 1px; height: 18px; background: var(--line); }
.toolbar .spacer { flex: 1; }
.toolbar .hint { font-size: 12px; color: var(--ink-3); }

/* ── 时间线 ── */
.timeline { display: flex; flex-direction: column; gap: 8px; }
.phase, .phase-wrap .phase {
    display: flex; align-items: center; gap: 10px; padding: 2px 4px;
    font-size: 12px; color: var(--ink-3); font-weight: 600;
}
.phase::before, .phase::after { content: ""; flex: 1; height: 1px; background: var(--line); }
.phase .t { font-weight: 400; font-variant-numeric: tabular-nums; }
.phase.clickable { cursor: pointer; }
.phase-more { color: var(--blue); font-weight: 400; }
.phase-detail {
    display: none; margin: 6px 20px 4px; padding: 10px 12px; background: white;
    border: 1px solid var(--line); border-radius: 8px;
    font-family: var(--mono); font-size: 11.5px; color: var(--ink-2);
    white-space: pre-wrap; word-break: break-all; max-height: 260px; overflow: auto;
}
.phase-wrap.open .phase-detail { display: block; }
.error-entry {
    padding: 8px 14px; background: var(--red-bg); border: 1px solid #fca5a5;
    border-radius: 10px; font-size: 12.5px; color: var(--red);
}
.error-entry .t { font-family: var(--mono); font-size: 11px; margin-right: 8px; color: var(--ink-3); }
.empty-logs { text-align: center; color: var(--ink-3); padding: 40px 0; }

/* ── 业务方法分组卡 ── */
.group {
    background: white; border: 1px solid var(--line); border-radius: 12px;
    overflow: hidden; box-shadow: 0 1px 2px rgba(15,23,42,.04);
}
.group.failed { border-color: #fca5a5; box-shadow: 0 1px 6px rgba(220,38,38,.08); }
/* 嵌套子卡片（AW 调用其它 AW） */
.group.sub { margin: 6px 14px 6px 40px; border-radius: 10px; border-left: 3px solid var(--line); }
.group.sub.failed { border-left-color: var(--red); }
.group.sub > .group-header { padding: 8px 12px; }
.group.sub .g-title { font-size: 13px; }
.group.sub .row { padding-left: 32px; }
.group-header {
    display: flex; align-items: center; gap: 10px; padding: 10px 14px;
    cursor: pointer; user-select: none; transition: background .15s;
}
.group-header:hover { background: #f8fafc; }
.chevron { color: var(--ink-3); font-size: 11px; transition: transform .2s; width: 12px; flex-shrink: 0; }
.group.open .chevron { transform: rotate(90deg); }
.g-icon {
    width: 24px; height: 24px; border-radius: 7px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700;
}
.group.ok .g-icon { background: var(--green-soft); color: var(--green); }
.group.failed .g-icon { background: var(--red-soft); color: var(--red); }
.g-title { font-weight: 650; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.g-method { font-family: var(--mono); font-size: 11.5px; color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.u-tag { color: white; padding: 2px 9px; border-radius: 6px; font-weight: 600; font-size: 11.5px; flex-shrink: 0; }
.g-meta { margin-left: auto; display: flex; align-items: center; gap: 14px; font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums; flex-shrink: 0; }
.g-meta .cnt b { color: var(--ink-2); }
.g-meta .cnt .f { color: var(--red); font-weight: 700; }
.g-dur { font-weight: 600; color: var(--ink-2); }
.group.failed .g-dur { color: var(--red); }
.g-bar { width: 64px; height: 4px; border-radius: 2px; background: var(--line); overflow: hidden; display: flex; }
.g-bar i { display: block; height: 100%; background: var(--green); }
.g-bar i.f { background: var(--red); }

/* ── 组内原子操作行 ── */
.rows { display: none; border-top: 1px solid var(--line); }
.group.open .rows { display: block; }
.row {
    display: flex; align-items: center; gap: 10px; padding: 6px 14px 6px 40px;
    font-size: 12.5px; cursor: pointer; border-top: 1px solid #f1f5f9; transition: background .1s;
}
.row:first-child { border-top: none; }
.row:hover { background: #f8fafc; }
.row.fail { background: var(--red-bg); }
.row.fail:hover { background: #fee2e2; }
.row .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); flex-shrink: 0; }
.row.fail .dot { background: var(--red); box-shadow: 0 0 0 3px rgba(220,38,38,.15); }
.r-time { font-family: var(--mono); font-size: 11px; color: var(--ink-3); width: 86px; flex-shrink: 0; }
.r-method { font-family: var(--mono); color: var(--ink); font-weight: 550; flex-shrink: 0; }
.r-args { font-family: var(--mono); color: var(--ink-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.row.fail .r-method, .row.fail .r-args { color: var(--red); }
.row.aw-log { background: #fffbeb; }
.row.aw-log:hover { background: #fef3c7; }
.row.aw-log .r-method { color: #b45309; }
.row.aw-log .r-args { color: #92400e; }
.log-dot { width: 7px; color: #f59e0b; font-size: 10px; flex-shrink: 0; }
.r-shot { font-size: 11px; color: var(--blue); flex-shrink: 0; }
.r-dur { font-family: var(--mono); font-size: 11px; color: var(--ink-3); width: 56px; text-align: right; flex-shrink: 0; }
.row.slow .r-dur { color: #d97706; font-weight: 700; }
.row-empty { padding: 12px 40px; font-size: 12px; color: var(--ink-3); }

/* ── 行详情 ── */
.row-detail { display: none; padding: 10px 14px 12px 40px; background: #fafbfc; border-top: 1px dashed var(--line); }
.row-detail.open { display: block; }
.row.fail + .row-detail { background: var(--red-bg); }
.kv { display: flex; gap: 12px; flex-wrap: wrap; }
.kv > div { flex: 1; min-width: 260px; }
.k { font-size: 10.5px; font-weight: 700; color: var(--ink-3); text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px; }
.row-detail .v, .err-box .v {
    background: white; border: 1px solid var(--line); border-radius: 8px;
    padding: 8px 10px; font-family: var(--mono); font-size: 11.5px; color: var(--ink-2);
    line-height: 1.55; word-break: break-all;
}
.code-block { margin: 0; white-space: pre-wrap; overflow: auto; max-height: 360px; }
.http-status {
    display: inline-block; margin-bottom: 5px; padding: 2px 7px; border-radius: 5px;
    font-family: var(--mono); font-size: 11px; font-weight: 700;
}
.http-ok { color: var(--green); background: var(--green-soft); }
.http-fail { color: var(--red); background: var(--red-soft); }
.http-body { max-height: 420px; }
.log-detail .v { white-space: pre-wrap; }
.err-box { margin-bottom: 10px; }
.err-box .v { border-color: #fca5a5; color: var(--red); }
.rid { font-family: var(--mono); font-size: 11px; color: var(--ink-3); margin: 6px 0; }
.ocr-box { margin-top: 10px; }
.ocr-chip { display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; background: #eef2ff; color: #4338ca; border-radius: 5px; font-size: 11px; font-family: var(--mono); }
.shots { display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.shot {
    width: 168px; height: 104px; border-radius: 8px; border: 1px solid var(--line);
    position: relative; cursor: zoom-in; overflow: hidden; background: #e2e8f0;
}
.shot img { width: 100%; height: 100%; object-fit: cover; display: block; }
.shot .cap {
    position: absolute; bottom: 0; left: 0; right: 0; background: rgba(15,23,42,.72);
    color: white; font-size: 10px; padding: 3px 8px;
}

/* ── 截图区 ── */
.screenshots-card {
    margin-top: 14px; background: white; border: 1px solid var(--line);
    border-radius: 12px; padding: 14px;
}
.sc-title { font-size: 13px; font-weight: 700; color: var(--ink-2); margin-bottom: 10px; }
.screenshots-card .shot { width: 220px; height: 136px; }

/* ── 图片弹窗 ── */
.modal {
    display: none; position: fixed; inset: 0; background: rgba(15,23,42,.85);
    z-index: 100; align-items: center; justify-content: center; cursor: zoom-out;
}
.modal.show { display: flex; }
.modal img { max-width: 92vw; max-height: 92vh; border-radius: 8px; }

/* ── 过滤态 ── */
body.only-fail .group.ok, body.only-fail .phase, body.only-fail .phase-wrap { display: none; }
body.filter-user .group:not(.match-user) { display: none; }
"""

# ── 交互脚本 ─────────────────────────────────────────────
_JS = """
function tg(h) { h.parentElement.classList.toggle('open'); }
function td(r) {
    const next = r.nextElementSibling;
    if (next && next.classList.contains('row-detail')) next.classList.toggle('open');
}
function tp(p) { p.parentElement.classList.toggle('open'); }
function toggleAll(open) {
    document.querySelectorAll('.group').forEach(g => g.classList.toggle('open', open));
}
function filterUser(btn, uid) {
    document.querySelectorAll('.ubtn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (!uid) {
        document.body.classList.remove('filter-user');
        document.querySelectorAll('.group').forEach(g => g.classList.remove('match-user'));
        return;
    }
    document.body.classList.add('filter-user');
    document.querySelectorAll('.group').forEach(g => {
        g.classList.toggle('match-user', g.dataset.user === uid);
    });
}
function showImage(src) {
    const modal = document.getElementById('modal');
    document.getElementById('modal-img').src = src;
    modal.classList.add('show');
}
document.getElementById('modal').addEventListener('click', function() {
    this.classList.remove('show');
});
"""
