"""HTML 报告生成器。"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


# OCR 相关方法集合（需要显示 ocr_info）
OCR_METHODS = {
    # OCR 方法
    "ocr_click", "ocr_input", "ocr_wait", "ocr_assert", "ocr_find",
    "ocr_exists", "ocr_get_text", "ocr_paste", "ocr_move", "ocr_double_click",
    "ocr_click_same_row_text", "ocr_check_same_row_text",
    # OCR 相关 Image 方法
    "image_click_near_text", "ocr_click_same_row_image", "ocr_check_same_row_image",
}


def should_show_ocr_info(method: str) -> bool:
    """判断是否需要显示 OCR 信息。

    Args:
        method: 方法名。

    Returns:
        True 如果需要显示 OCR 信息。
    """
    return method in OCR_METHODS


class HTMLReportGenerator:
    """HTML 报告生成器。"""

    @staticmethod
    def _clean_text_for_display(text: str) -> str:
        """清理文本内容，只过滤 base64 数据，保留其他内容。

        Args:
            text: 原始文本。

        Returns:
            清理后的文本，base64 数据被替换为占位符。
        """
        if not text:
            return ""
        # 检测并替换 PNG base64（以 iVBORw0KGgo 开头）
        import re
        # PNG base64 特征：iVBORw0KGgo 开头，后面是长字符串
        base64_pattern = r'iVBORw0KGgo[A-Za-z0-9+/=]{100,}'
        cleaned = re.sub(base64_pattern, '[截图数据]', text)
        return cleaned

    @staticmethod
    def _clean_response_for_display(response: Dict[str, Any]) -> Dict[str, Any]:
        """清理响应数据，移除大型 base64 数据用于显示。

        Args:
            response: 原始响应数据。

        Returns:
            清理后的响应数据，适合在报告中显示。
        """
        if not isinstance(response, dict):
            return response

        cleaned = {}
        for key, value in response.items():
            if key == "screenshots":
                # 截图数据不显示，只显示数量
                count = len(value) if isinstance(value, list) else 0
                if count > 0:
                    cleaned[key] = f"[{count}张截图]"
            elif key == "error_screenshot" and isinstance(value, str) and len(value) > 100:
                # 错误截图不显示在文字中
                cleaned[key] = "[错误截图]"
            elif key == "actions" and isinstance(value, list):
                # 清理 actions 中的 screenshot 数据
                cleaned[key] = []
                for action in value:
                    if isinstance(action, dict):
                        clean_action = {}
                        for ak, av in action.items():
                            if ak in ("screenshot", "error_screenshot") and isinstance(av, str) and len(av) > 100:
                                clean_action[ak] = "[截图数据]"
                            elif ak == "output" and isinstance(av, str) and len(av) > 500:
                                # 可能是 base64 输出
                                clean_action[ak] = "[输出数据]"
                            else:
                                clean_action[ak] = av
                        cleaned[key].append(clean_action)
                    else:
                        cleaned[key].append(value)
            else:
                cleaned[key] = value
        return cleaned

    @staticmethod
    def _format_duration(duration_ms: int) -> str:
        """格式化耗时显示，超过1秒显示为秒。

        Args:
            duration_ms: 耗时（毫秒）。

        Returns:
            格式化后的耗时字符串，如 "1.5s" 或 "800ms"。
        """
        if duration_ms >= 1000:
            return f"{duration_ms / 1000:.1f}s"
        return f"{duration_ms}ms"

    @staticmethod
    def _get_user_color(user_id: str) -> str:
        """根据用户 ID 返回标签颜色。

        Args:
            user_id: 用户 ID，如 "userA"、"userB"。

        Returns:
            颜色十六进制值，如 "#3b82f6"。
        """
        colors = {
            "userA": "#3b82f6",  # 蓝色
            "userB": "#22c55e",  # 绿色
            "userC": "#8b5cf6",  # 紫色
            "userD": "#f59e0b",  # 黄色
        }
        # 处理 _api 后缀的用户（如 userA_api）
        base_user_id = user_id.replace("_api", "")
        return colors.get(base_user_id, "#6b7280")  # 默认灰色

    @staticmethod
    def _format_timeline_title(aw_name: str, method: str, args: Dict[str, Any]) -> str:
        """格式化时间线步骤标题，简化显示。

        Args:
            aw_name: AW 类名（如 LoginAW）。
            method: 方法名（如 do_login）。
            args: 调用参数。

        Returns:
            简化的标题，如 "登录系统" 或 "ocr_wait(text=\"登录\")"。
        """
        # 业务方法（do_*/should_*）：只显示方法名对应的中文描述
        if method.startswith(('do_', 'should_')):
            # 从方法名提取动作
            action = method.replace('do_', '').replace('should_', '')
            # 常见动作映射
            action_map = {
                'login': '登录系统',
                'logout': '退出登录',
                'join_as_host': '作为主持人入会',
                'join_as_guest': '作为访客入会',
                'leave': '离开会议',
                'admit_participant': '准入参会者',
                'create_meeting': '创建会议',
                'cancel_meeting': '取消会议',
                'set_waiting_room': '设置等候室',
                'login_success': '断言登录成功',
                'join_success': '断言入会成功',
                'in_waitingroom': '断言在等候室',
            }
            return action_map.get(action, method)

        # 原子操作：显示方法名和关键参数
        DISPLAY_ARGS = {
            "text", "label", "content", "image_path", "key", "url",
            "app_id", "x", "y", "from_x", "from_y", "to_x", "to_y",
            "duration_ms", "timeout", "index", "confidence", "name",
            "command", "page_index", "monitor"
        }

        filtered_args = {
            k: v for k, v in args.items()
            if k in DISPLAY_ARGS and v is not None
        }

        if not filtered_args:
            return method

        parts = []
        for k, v in filtered_args.items():
            if isinstance(v, str) and len(v) > 20:
                v = v[:17] + "..."
            parts.append(f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}")

        return f"{method}({', '.join(parts)})"

    @staticmethod
    def _render_timeline_step(log: Dict[str, Any]) -> str:
        """渲染单个时间线步骤。

        Args:
            log: 日志数据。

        Returns:
            HTML 字符串。
        """
        # 提取信息
        time_str = log.get("time", "")
        args = log.get("args", {})
        user_id = args.get("user_id", "")
        user_name = args.get("user_name", "")
        user_account = args.get("user_account", "")
        user_ip = args.get("user_ip", "")
        aw_name = log.get("aw_name", "")
        method = log.get("method", "")
        duration = log.get("duration_ms", 0)
        success = log.get("success", True)
        request_id = log.get("request_id", "")
        result = log.get("result", {})

        # 格式化
        duration_str = HTMLReportGenerator._format_duration(duration)
        user_color = HTMLReportGenerator._get_user_color(user_id)
        title = HTMLReportGenerator._format_timeline_title(aw_name, method, args)

        # 状态图标和样式
        status_icon = "✓" if success else "✗"
        status_color = "#22c55e" if success else "#ef4444"

        # 用户信息行
        user_info_parts = []
        if user_name:
            user_info_parts.append(user_name)
        if user_account:
            user_info_parts.append(user_account)
        if user_ip:
            user_info_parts.append(user_ip)
        user_info_str = " · ".join(user_info_parts) if user_info_parts else user_id

        # 清理参数和响应用于显示
        clean_args = {k: v for k, v in args.items() if k not in (
            "user_id", "user_account", "user_name", "user_ip",
            "target_image", "image_base64", "screenshot", "error_screenshot"
        )}
        clean_result = HTMLReportGenerator._clean_response_for_display(result)

        # 构建展开详情
        detail_parts = []

        # request_id
        if request_id:
            detail_parts.append(f'<div class="detail-item"><strong>request_id:</strong> {request_id}</div>')

        # 错误信息（失败时）
        if not success:
            error_msg = result.get("error", "")
            if error_msg:
                detail_parts.append(f'''
            <div class="step-error-box">
                <div class="step-error-label">错误信息</div>
                <div class="step-error-text">{HTMLReportGenerator._clean_text_for_display(error_msg)}</div>
            </div>''')

        # OCR 信息（OCR 相关方法时显示）
        ocr_info = result.get("ocr_info", [])
        if ocr_info and isinstance(ocr_info, list) and len(ocr_info) > 0:
            # 判断是否是 OCR 相关方法
            if should_show_ocr_info(method):
                ocr_items = []
                for item in ocr_info:
                    text = item.get("text", "")
                    center = item.get("center", {})
                    x = center.get("x", "-")
                    y = center.get("y", "-")
                    if text:
                        ocr_items.append(f'<span class="ocr-text-item">"{text}" ({x}, {y})</span>')
                if ocr_items:
                    detail_parts.append(f'''
            <div class="step-ocr-box">
                <div class="step-ocr-label">OCR 识别结果</div>
                <div class="step-ocr-content">{"".join(ocr_items)}</div>
            </div>''')

        # 请求和响应
        if clean_args or clean_result:
            detail_parts.append('<div class="detail-row">')
            if clean_args:
                detail_parts.append(f'''
                <div class="detail-half">
                    <div class="detail-label">请求</div>
                    <div class="detail-content">{clean_args}</div>
                </div>''')
            if clean_result:
                detail_parts.append(f'''
                <div class="detail-half">
                    <div class="detail-label">响应</div>
                    <div class="detail-content">{clean_result}</div>
                </div>''')
            detail_parts.append('</div>')

        # 截图（失败时）
        if not success:
            error_screenshot = result.get("error_screenshot", "")
            target_image = log.get("target_image", "")

            screenshots_html = ""
            if error_screenshot and len(error_screenshot) > 100:
                screenshots_html += f'''
                <div class="step-screenshot-item" onclick="showImage('{error_screenshot}')">
                    <img src="data:image/png;base64,{error_screenshot}">
                    <div class="step-screenshot-label">当前屏幕</div>
                </div>'''
            if target_image and len(target_image) > 100:
                screenshots_html += f'''
                <div class="step-screenshot-item" onclick="showImage('{target_image}')">
                    <img src="data:image/png;base64,{target_image}">
                    <div class="step-screenshot-label">目标图片</div>
                </div>'''

            if screenshots_html:
                detail_parts.append(f'''
            <div class="screenshots-row">
                <div class="screenshots-label">失败截图</div>
                <div class="screenshots-grid">{screenshots_html}</div>
            </div>''')

        detail_html = "".join(detail_parts)

        # CSS 类
        step_class = "timeline-step success"
        if not success:
            step_class = "timeline-step failed-step"

        return f'''
    <div class="{step_class}">
        <div class="step-header" onclick="toggleStep(this)">
            <div class="step-icon">{status_icon}</div>
            <span class="step-user" style="background:{user_color}">{user_id}</span>
            <span class="step-time">{time_str}</span>
            <span class="step-duration" style="color:{status_color}">{duration_str}</span>
            <span class="step-divider"></span>
            <span class="step-user-info" style="color:{'#7f1d1d' if not success else '#9ca3af'}">{user_info_str}</span>
            <span class="step-title{' failed-text' if not success else ''}">{title}</span>
        </div>
        <div class="step-detail {'expanded' if not success else ''}">
            {detail_html}
        </div>
    </div>'''
    @staticmethod
    def generate(
        report_path: Path,
        case_name: str,
        case_title: str = "",
        logs: List[Dict[str, Any]] = [],
        duration_ms: int = 0,
        status: str = "passed",
        error_msg: str = "",
        is_api_failure: bool = False
    ) -> None:
        """生成 HTML 报告。"""
        failed_aw_steps = HTMLReportGenerator._get_failed_aw_steps(logs)
        logs_html = HTMLReportGenerator._build_logs_html(logs)
        screenshots_html = HTMLReportGenerator._build_screenshots_html(logs, is_api_failure)

        failed_steps_html = ""
        if failed_aw_steps:
            steps_list = "".join([f"<li>{step}</li>" for step in failed_aw_steps])
            failed_steps_html = f"""
            <div class="failed-steps">
                <div class="failed-steps-title">❌ 失败步骤</div>
                <ul class="failed-steps-list">{steps_list}</ul>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{case_name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8fafc;
            min-height: 100vh;
            margin: 0;
            padding: 24px 16px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        /* 报告头部 */
        .header {{
            background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
            border-radius: 16px;
            padding: 24px 28px;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(34,197,94,0.1);
        }}
        .header.failed {{
            background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
            box-shadow: 0 4px 20px rgba(239,68,68,0.1);
        }}
        .header-content {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }}
        .header-left {{ flex: 1; }}
        .header h1 {{ margin: 0 0 6px 0; font-size: 24px; color: #166534; font-weight: 700; }}
        .header.failed h1 {{ color: #dc2626; }}
        .header h2 {{ margin: 0; font-size: 15px; color: #15803d; font-weight: 400; }}
        .header.failed h2 {{ color: #b91c1c; }}
        .header-right {{ display: flex; align-items: center; gap: 20px; }}
        .status-badge {{
            padding: 12px 24px;
            border-radius: 24px;
            font-weight: 600;
            font-size: 16px;
        }}
        .status-passed {{ background: #22c55e; color: white; }}
        .status-failed {{ background: #ef4444; color: white; }}
        .header-meta {{ text-align: right; }}
        .header-meta .duration {{ font-size: 22px; font-weight: 700; color: #166534; }}
        .header.failed .header-meta .duration {{ color: #dc2626; }}
        .header-meta .time {{ font-size: 13px; color: #6b7280; margin-top: 4px; }}

        /* 失败提示 */
        .failed-steps {{
            margin-top: 14px;
            padding: 12px 16px;
            background: white;
            border-radius: 10px;
            border-left: 4px solid #ef4444;
        }}
        .failed-steps-title {{ font-weight: 600; color: #dc2626; margin-bottom: 8px; font-size: 14px; }}
        .failed-steps-list {{ margin: 0; padding-left: 20px; color: #7f1d1d; font-size: 13px; }}
        .failed-steps-list li {{ margin: 6px 0; }}

        .error-box {{
            margin-top: 14px;
            padding: 12px 16px;
            background: white;
            border-radius: 10px;
            border-left: 4px solid #ef4444;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #dc2626;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 150px;
            overflow: auto;
        }}

        /* 时间线步骤 */
        .timeline-card {{
            background: white;
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}
        .timeline-title {{
            font-size: 14px;
            color: #374151;
            padding: 8px 12px;
            font-weight: 600;
            border-bottom: 1px solid #e5e7eb;
        }}

        .timeline-step {{
            margin: 10px 0;
            border-radius: 12px;
            background: white;
            border: 1px solid #e5e7eb;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        .timeline-step:last-child {{ margin-bottom: 0; }}
        .timeline-step.success {{ border-color: #bbf7d0; }}
        .timeline-step.failed-step {{
            border-color: #fecaca;
            background: linear-gradient(to right, #fef2f2, white);
        }}

        .step-header {{
            padding: 14px 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 14px;
            transition: background 0.15s;
        }}
        .timeline-step.success .step-header {{ background: linear-gradient(to right, #f0fdf4, white); }}
        .timeline-step.failed-step .step-header {{ background: linear-gradient(to right, #fef2f2, white); }}
        .step-header:hover {{ filter: brightness(0.98); }}

        .step-icon {{
            width: 32px;
            height: 32px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            flex-shrink: 0;
        }}
        .timeline-step.success .step-icon {{ background: #dcfce7; color: #22c55e; }}
        .timeline-step.failed-step .step-icon {{ background: #fee2e2; color: #ef4444; }}
        .step-icon-blue {{ background: #dbeafe; color: #1d4ed8; }}

        /* 步骤卡片样式（step 类型日志） */
        .timeline-step.step-block {{ border-color: #dbeafe; }}
        .timeline-step.step-block .step-header {{ background: linear-gradient(to right, #eff6ff, white); }}
        .timeline-step.step-block .step-detail {{ background: #eff6ff; }}

        .step-status {{ font-size: 16px; font-weight: 600; }}
        .step-user {{
            color: white;
            padding: 3px 10px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
        }}
        .step-time {{ color: #6b7280; font-size: 13px; width: 70px; }}
        .step-duration {{ font-size: 13px; }}
        .step-divider {{
            width: 1px;
            height: 18px;
            background: #d1d5db;
            margin-left: 4px;
        }}
        .step-user-info {{ font-size: 13px; }}
        .step-title {{
            flex: 1;
            font-weight: 500;
            padding-left: 14px;
        }}
        .step-title.failed-text {{ color: #dc2626; }}

        /* 展开详情 */
        .step-detail {{
            display: none;
            padding: 12px 14px;
            border-top: 1px solid #e5e7eb;
        }}
        .step-detail.expanded {{ display: block; }}
        .timeline-step.success .step-detail {{ background: #f0fdf4; }}
        .timeline-step.failed-step .step-detail {{ background: #fef2f2; border-top-color: #fecaca; }}

        .detail-item {{ font-size: 12px; color: #6b7280; margin-bottom: 8px; }}
        .detail-label {{ font-size: 11px; color: #6b7280; font-weight: 600; margin-bottom: 4px; }}
        .detail-content {{
            background: white;
            padding: 8px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #4b5563;
        }}
        .detail-json {{
            background: white;
            padding: 12px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #4b5563;
            white-space: pre;
            overflow-x: auto;
            margin: 0;
            line-height: 1.5;
        }}

        .step-error-label {{ font-size: 11px; color: #dc2626; font-weight: 600; margin-bottom: 4px; }}
        .step-error-text {{
            background: white;
            padding: 8px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #dc2626;
        }}
        .step-error-box {{ margin-bottom: 10px; }}

        /* OCR 信息样式 */
        .step-ocr-box {{ margin-bottom: 10px; }}
        .step-ocr-label {{ font-size: 11px; color: #6b7280; font-weight: 600; margin-bottom: 4px; }}
        .step-ocr-content {{
            background: white;
            padding: 8px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #4b5563;
            line-height: 1.6;
        }}
        .ocr-text-item {{
            display: inline-block;
            margin: 3px 5px;
            padding: 3px 8px;
            background: #f3f4f6;
            border-radius: 4px;
        }}

        .detail-row {{ display: flex; gap: 14px; margin-bottom: 10px; }}
        .detail-half {{ flex: 1; }}

        .screenshots-row {{ margin-top: 10px; }}
        .screenshots-label {{ font-size: 11px; color: #6b7280; font-weight: 600; margin-bottom: 6px; }}
        .screenshots-grid {{ display: flex; gap: 10px; }}
        .step-screenshot-item {{
            width: 120px;
            height: 80px;
            background: #e5e7eb;
            border-radius: 6px;
            cursor: pointer;
            position: relative;
            border: 1px solid #fecaca;
        }}
        .step-screenshot-item img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 6px;
        }}
        .step-screenshot-label {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(0,0,0,0.6);
            color: white;
            font-size: 10px;
            padding: 3px 6px;
            text-align: center;
            border-radius: 0 0 6px 6px;
        }}

        /* 截图卡片 */
        .screenshots-card {{
            background: white;
            border-radius: 16px;
            padding: 24px;
            margin-top: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}
        .screenshots-card h3 {{ margin: 0 0 16px 0; font-size: 16px; color: #374151; font-weight: 600; }}

        /* 弹窗 */
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 1000;
            cursor: zoom-out;
        }}
        .modal.show {{ display: flex; align-items: center; justify-content: center; }}
        .modal img {{ max-width: 95%; max-height: 95%; border-radius: 8px; }}
        .modal-close {{ position: fixed; top: 20px; right: 30px; color: white; font-size: 40px; cursor: pointer; }}

        .empty-logs {{ padding: 24px; text-align: center; color: #868e96; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header {'failed' if status == 'failed' else ''}">
            <div class="header-content">
                <div class="header-left">
                    <h1>{case_name}</h1>
                    {f'<h2>{case_title}</h2>' if case_title else ''}
                </div>
                <div class="header-right">
                    <span class="status-badge {'status-passed' if status == 'passed' else 'status-failed'}">
                        {'✓ 通过' if status == 'passed' else '✗ 失败'}
                    </span>
                    <div class="header-meta">
                        <div class="duration">{HTMLReportGenerator._format_duration(duration_ms)}</div>
                        <div class="time">{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
                    </div>
                </div>
            </div>
            {failed_steps_html}
            {f'<div class="error-box">{error_msg}</div>' if error_msg else ''}
        </div>

        <div class="timeline-card">
            <div class="timeline-title">执行步骤</div>
            {logs_html}
        </div>

        {screenshots_html}
    </div>

    <div id="modal" class="modal">
        <span class="modal-close">&times;</span>
        <img id="modal-img" src="">
    </div>

    <script>
        function showImage(base64) {{
            document.getElementById('modal-img').src = 'data:image/png;base64,' + base64;
            document.getElementById('modal').classList.add('show');
        }}

        function toggleStep(header) {{
            const step = header.closest('.timeline-step');
            const detail = step.querySelector('.step-detail');
            detail.classList.toggle('expanded');
        }}

        // 点击弹窗关闭
        document.getElementById('modal').addEventListener('click', function() {{
            this.classList.remove('show');
        }});
    </script>
</body>
</html>"""

        report_path.write_text(html, encoding="utf-8")

    @staticmethod
    def _get_failed_aw_steps(logs: List[Dict[str, Any]]) -> List[str]:
        """提取失败的 AW 步骤名称。"""
        failed_steps = []
        for log in logs:
            if log.get("type") == "aw_call" and not log.get("success"):
                aw_name = log.get("aw_name", "")
                method = log.get("method", "")
                failed_steps.append(f"{aw_name}.{method}()")
        return failed_steps

    @staticmethod
    def _build_logs_html(logs: List[Dict[str, Any]]) -> str:
        """构建时间线步骤列表 HTML。

        Args:
            logs: 日志列表。

        Returns:
            HTML 字符串。
        """
        # 构建所有日志项，统一按时间排序
        log_items: List[tuple] = []  # (time_str, html)

        # 处理 aw_call 类型日志
        for log in logs:
            if log.get("type") != "aw_call":
                continue
            time_str = log.get("time", "")
            html = HTMLReportGenerator._render_timeline_step(log)
            log_items.append((time_str, html))

        # 处理 step 类型日志（如"申请用户资源"，排除 hook 日志避免重复）
        for log in logs:
            log_type = log.get("type", "")
            time_str = log.get("time", "")

            if log_type == "step":
                step_name = log.get('step', '')
                # 排除 hook 日志（aw_call 中已有对应操作）
                if step_name.startswith('执行 hook:'):
                    continue
                detail = log.get('detail', '')
                clean_detail = HTMLReportGenerator._clean_text_for_display(detail) if detail else ""

                # 判断是否是 JSON 格式（包含换行和缩进），使用 pre 标签保留格式
                if clean_detail and ('\n' in clean_detail or clean_detail.startswith('{') or clean_detail.startswith('[')):
                    detail_html = f'<div class="step-detail"><pre class="detail-json">{clean_detail}</pre></div>'
                elif clean_detail:
                    detail_html = f'<div class="step-detail"><div class="detail-content">{clean_detail}</div></div>'
                else:
                    detail_html = ''

                html = f'''
    <div class="timeline-step step-block">
        <div class="step-header" onclick="toggleStep(this)">
            <div class="step-icon step-icon-blue">▶</div>
            <span class="step-title">{step_name}</span>
            <span class="step-time">{time_str}</span>
        </div>
        {detail_html}
    </div>'''
                log_items.append((time_str, html))

        # 按时间排序
        log_items.sort(key=lambda x: x[0] or "")

        if not log_items:
            return '<div class="empty-logs">暂无执行步骤</div>'

        return "\n".join(item[1] for item in log_items)

    @staticmethod
    def _build_screenshots_html(logs: List[Dict[str, Any]], is_api_failure: bool = False) -> str:
        """构建截图区域 HTML。

        只显示步骤中没有截图的用户，避免重复显示。

        Args:
            logs: 日志列表。
            is_api_failure: 是否是 API AW 失败。

        Returns:
            截图区域 HTML。
        """
        # 获取所有失败截图
        screenshots = [log for log in logs if log.get("type") == "screenshot"]

        if not screenshots:
            return ""

        # 找出步骤中已有截图的用户
        users_with_step_screenshot = set()
        for log in logs:
            if log.get("type") == "aw_call":
                result = log.get("result", {})
                has_screenshot = False

                # 检查 error_screenshot（失败时的错误截图）
                error_screenshot = result.get("error_screenshot", "")
                if error_screenshot and len(error_screenshot) > 100:
                    has_screenshot = True

                # 检查 actions 中的截图
                if not has_screenshot:
                    actions = result.get("actions", [])
                    for action in actions:
                        screenshot = action.get("screenshot", "")
                        if screenshot and len(screenshot) > 100:
                            has_screenshot = True
                            break

                if has_screenshot:
                    # 从 args 中获取用户ID
                    args = log.get("args", {})
                    user_id = args.get("user_id", "")
                    if user_id:
                        users_with_step_screenshot.add(user_id)

        # 只显示步骤中没有截图的用户
        filtered_screenshots = [
            shot for shot in screenshots
            if shot.get("user_id", "") not in users_with_step_screenshot
        ]

        if not filtered_screenshots:
            return ""

        items = []
        for shot in filtered_screenshots:
            base64_data = shot.get("base64", "")
            user_id = shot.get("user_id", "")
            items.append(f"""
                <div class="step-screenshot-item" onclick="showImage('{base64_data}')">
                    <img src="data:image/png;base64,{base64_data}" alt="{user_id}">
                    <div class="step-screenshot-label">📷 {user_id}</div>
                </div>""")

        # 根据失败来源决定标题
        title = "📸 用户截图" if is_api_failure else "📸 其他用户截图"

        return f"""
        <div class="screenshots-card">
            <h3>{title}</h3>
            <div class="screenshots-grid">
                {"".join(items)}
            </div>
        </div>"""