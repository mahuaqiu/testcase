"""HTML 报告生成器。"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


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
    def _format_aw_title(aw_name: str, method: str, args: Dict[str, Any]) -> str:
        """格式化 AW 标题，显示关键参数。

        Args:
            aw_name: AW 类名。
            method: 方法名。
            args: 调用参数。

        Returns:
            格式化后的标题，如 "LoginAW.do_login(text=\"登录\")"。
        """
        # 需要显示的参数名（复用 report_logger.py 的逻辑）
        DISPLAY_ARGS = {
            "text", "label", "content", "image_path", "key", "url",
            "app_id", "x", "y", "from_x", "from_y", "to_x", "to_y",
            "duration_ms", "timeout", "index", "confidence",
            # 业务方法常见参数
            "username", "password", "subject", "meeting_id", "name",
            "title", "message", "file_path", "wait_time"
        }

        # 移除用户信息字段（已在折叠标题中显示）
        HIDDEN_ARGS = {
            "platform", "user_id", "user_account", "user_name",
            "target_image", "image_base64", "screenshot"
        }

        # 过滤参数
        filtered_args = {
            k: v for k, v in args.items()
            if k in DISPLAY_ARGS and k not in HIDDEN_ARGS
        }

        # 格式化参数
        if not filtered_args:
            return f"{aw_name}.{method}()"

        parts = []
        for k, v in filtered_args.items():
            # 跳过 None 值
            if v is None:
                continue
            if isinstance(v, str):
                # 字符串过长时截断显示
                display_v = v if len(v) <= 20 else v[:17] + "..."
                parts.append(f'{k}="{display_v}"')
            else:
                parts.append(f"{k}={v}")

        # 如果过滤后没有参数，返回空括号
        if not parts:
            return f"{aw_name}.{method}()"

        return f"{aw_name}.{method}({', '.join(parts)})"

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
    def _build_aw_tree(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将日志按 parent_aw + user_id 分组构建树形结构。

        Args:
            logs: 原始日志列表。

        Returns:
            块列表，每个块包含业务方法信息和子步骤列表。
        """
        # 先找出所有业务方法日志（用于提取参数和状态）
        # block_id 格式：{aw_name}.{method}#{user_id}
        business_method_logs: Dict[str, Dict[str, Any]] = {}
        for log in logs:
            if log.get("type") != "aw_call":
                continue
            if log.get("is_business_method"):
                args = log.get("args", {})
                user_id = args.get("user_id", "")
                block_id = f"{log.get('aw_name', '')}.{log.get('method', '')}"
                if user_id:
                    block_id = f"{block_id}#{user_id}"
                business_method_logs[block_id] = log

        # 按 parent_aw + user_id 分组原子操作日志
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for log in logs:
            if log.get("type") != "aw_call":
                continue
            if log.get("is_business_method"):
                continue  # 业务方法日志单独处理
            parent = log.get("parent_aw", "")
            # 如果有 parent_aw，需要加上 user_id 来区分不同用户
            if parent:
                args = log.get("args", {})
                user_id = args.get("user_id", "")
                if user_id:
                    parent = f"{parent}#{user_id}"
            if parent not in groups:
                groups[parent] = []
            groups[parent].append(log)

        # 构建业务方法块（parent_aw != "" 的日志属于某个业务方法）
        business_blocks: Dict[str, Dict[str, Any]] = {}

        for block_key, steps in groups.items():
            if block_key == "":
                continue  # 顶层原子操作，后面处理

            # 从 block_key 解析 aw_name, method, user_id
            # 格式：{aw_name}.{method}#{user_id}
            user_id = ""
            if "#" in block_key:
                parent_aw, user_id = block_key.rsplit("#", 1)
            else:
                parent_aw = block_key

            # 从 parent_aw 解析 aw_name 和 method
            parts = parent_aw.rsplit(".", 1)
            if len(parts) != 2:
                continue
            aw_name, method = parts

            # 从业务方法日志提取参数和状态（优先使用业务方法日志的状态）
            business_log = business_method_logs.get(block_key, {})
            business_args = business_log.get("args", {}) if business_log else {}
            # 优先使用业务方法日志的成功状态（处理业务方法本身抛异常的情况）
            if business_log:
                business_success = business_log.get("success", True)
                business_duration = business_log.get("duration_ms", 0)
                business_result = business_log.get("result", {})
            else:
                business_success = True
                business_duration = 0
                business_result = {}

            # 计算整体状态：如果业务方法失败，整体失败；否则看子步骤
            if not business_success:
                all_success = False
                total_duration = business_duration  # 使用业务方法耗时
            else:
                all_success = all(s.get("success", True) for s in steps)
                total_duration = sum(s.get("duration_ms", 0) for s in steps)

            # 从第一个步骤或业务方法日志获取用户信息
            first_step = steps[0] if steps else {}
            step_args = first_step.get("args", {}) if first_step else {}
            user_info = {
                "user_id": user_id or step_args.get("user_id", "") or business_args.get("user_id", ""),
                "user_name": step_args.get("user_name", "") or business_args.get("user_name", ""),
                "user_account": step_args.get("user_account", "") or business_args.get("user_account", ""),
                "user_ip": step_args.get("user_ip", "") or business_args.get("user_ip", ""),
            }

            # 时间：优先使用业务方法日志时间，其次使用第一个步骤时间
            time_str = business_log.get("time", "") if business_log else first_step.get("time", "")

            business_blocks[block_key] = {
                "block_id": block_key,
                "aw_name": aw_name,
                "method": method,
                "args": business_args,  # 业务方法参数
                "user_info": user_info,
                "success": all_success,
                "duration_ms": total_duration,
                "steps": steps,
                "time": time_str,
                "business_result": business_result,  # 保存业务方法结果（用于显示错误）
            }

        # 构建顶层块列表（parent_aw == "" 的原子操作 + 业务方法块）
        top_blocks: List[Dict[str, Any]] = []

        # 添加顶层原子操作（不属于任何业务方法）
        for log in groups.get("", []):
            aw_name = log.get("aw_name", "")
            method = log.get("method", "")
            args = log.get("args", {})
            user_id = args.get("user_id", "")
            block_id = f"{aw_name}.{method}"
            if user_id:
                block_id = f"{block_id}#{user_id}"

            user_info = {
                "user_id": user_id,
                "user_name": args.get("user_name", ""),
                "user_account": args.get("user_account", ""),
                "user_ip": args.get("user_ip", ""),
            }

            top_blocks.append({
                "block_id": block_id,
                "aw_name": aw_name,
                "method": method,
                "args": args,
                "user_info": user_info,
                "success": log.get("success", True),
                "duration_ms": log.get("duration_ms", 0),
                "steps": [],  # 无子步骤
                "time": log.get("time", ""),
                "single_step": True,  # 标记为单步骤块
                "step_data": log,  # 保存原始日志数据
            })

        # 添加业务方法块
        for block_id, block in business_blocks.items():
            top_blocks.append(block)

        # 添加没有子步骤但失败的业务方法（直接抛异常的情况）
        # 这些业务方法日志没有被 groups 收集（因为没有子步骤）
        for block_id, business_log in business_method_logs.items():
            if block_id in business_blocks:
                continue  # 已处理
            if business_log.get("success", True):
                continue  # 成功的不需要单独处理

            # 失败的业务方法，没有子步骤
            args = business_log.get("args", {})
            user_info = {
                "user_id": args.get("user_id", ""),
                "user_name": args.get("user_name", ""),
                "user_account": args.get("user_account", ""),
                "user_ip": args.get("user_ip", ""),
            }

            aw_name = business_log.get("aw_name", "")
            method = business_log.get("method", "")

            top_blocks.append({
                "block_id": block_id,
                "aw_name": aw_name,
                "method": method,
                "args": args,
                "user_info": user_info,
                "success": False,
                "duration_ms": business_log.get("duration_ms", 0),
                "steps": [],  # 无子步骤
                "time": business_log.get("time", ""),
                "single_step": True,
                "step_data": business_log,  # 用业务方法日志作为"步骤数据"
                "business_result": business_log.get("result", {}),
            })

        # 按时间排序
        top_blocks.sort(key=lambda b: b.get("time") or "")

        return top_blocks

    @staticmethod
    def _format_step_title(method: str, args: Dict[str, Any]) -> str:
        """格式化步骤标题，显示关键参数。

        Args:
            method: 方法名。
            args: 调用参数。

        Returns:
            格式化后的标题，如 "ocr_wait(text=\"登录\")"。
        """
        DISPLAY_ARGS = {
            "text", "label", "content", "image_path", "key", "url",
            "app_id", "x", "y", "from_x", "from_y", "to_x", "to_y",
            "duration_ms", "timeout", "index", "confidence"
        }

        HIDDEN_ARGS = {
            "platform", "user_id", "user_account", "user_name",
            "target_image", "image_base64", "screenshot"
        }

        filtered_args = {
            k: v for k, v in args.items()
            if k in DISPLAY_ARGS and k not in HIDDEN_ARGS
        }

        if not filtered_args:
            return f"{method}()"

        parts = []
        for k, v in filtered_args.items():
            if isinstance(v, str):
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")

        return f"{method}({', '.join(parts)})"

    @staticmethod
    def _render_aw_step(step: Dict[str, Any], is_last: bool = False) -> str:
        """渲染单个原子操作步骤。

        Args:
            step: 步骤日志数据。

        Returns:
            HTML 字符串。
        """
        success = step.get("success", True)
        status_class = "success" if success else "failed"
        status_text = "✓" if success else "✗"

        method = step.get("method", "")
        args = step.get("args", {})
        step_title = HTMLReportGenerator._format_step_title(method, args)
        duration = step.get("duration_ms", 0)
        duration_str = HTMLReportGenerator._format_duration(duration)

        clean_args = {k: v for k, v in args.items() if k not in ("user_id", "user_account", "user_name", "target_image", "image_base64", "screenshot", "error_screenshot")}
        # 对 args 值做进一步清理，只过滤 base64
        if clean_args:
            clean_args = {k: HTMLReportGenerator._clean_text_for_display(str(v)) if isinstance(v, str) and "iVBORw0KGgo" in v else v for k, v in clean_args.items()}
        clean_result = HTMLReportGenerator._clean_response_for_display(step.get("result", {}))

        detail_parts = []
        if clean_args:
            detail_parts.append(f"参数: {clean_args}")
        if clean_result:
            detail_parts.append(f"结果: {clean_result}")
        detail_html = "<br>".join(detail_parts)

        # 失败时展示截图
        screenshots_html = ""
        if not success:
            result = step.get("result", {})
            error_screenshot = result.get("error_screenshot", "")
            target_image = step.get("target_image", "")
            error_msg = result.get("error", "")

            screenshot_imgs = []
            if error_screenshot and len(error_screenshot) > 100:
                screenshot_imgs.append(f'''
                <div class="step-screenshot-wrapper">
                    <img src="data:image/png;base64,{error_screenshot}" class="step-screenshot" onclick="showImage('{error_screenshot}')">
                    <div class="step-screenshot-label">当前屏幕</div>
                </div>''')
            if target_image and len(target_image) > 100:
                screenshot_imgs.append(f'''
                <div class="step-screenshot-wrapper">
                    <img src="data:image/png;base64,{target_image}" class="step-screenshot" onclick="showImage('{target_image}')">
                    <div class="step-screenshot-label">目标图片</div>
                </div>''')

            if screenshot_imgs:
                screenshots_html = f'<div class="step-screenshots">{"".join(screenshot_imgs)}</div>'

            # 错误信息
            if error_msg:
                detail_html += f'<div class="step-error">{error_msg}</div>'

        return f'''
        <div class="aw-step {status_class}">
            <span class="step-status {status_class}">{status_text}</span>
            <span class="step-title">{step_title}</span>
            <span class="step-duration">{duration_str}</span>
            <div class="step-detail">{detail_html}</div>
            {screenshots_html}
        </div>'''

    @staticmethod
    def _render_aw_block(block: Dict[str, Any]) -> str:
        """渲染业务方法块（包含子步骤）。

        Args:
            block: 块数据。

        Returns:
            HTML 字符串。
        """
        success = block.get("success", True)
        item_class = "success" if success else "failed"
        expanded_class = "expanded" if not success else ""

        aw_name = block.get("aw_name", "")
        method = block.get("method", "")
        args = block.get("args", {})
        user_info = block.get("user_info", {})
        duration = block.get("duration_ms", 0)
        time_str = block.get("time", "")

        block_title = HTMLReportGenerator._format_aw_title(aw_name, method, args)
        duration_str = HTMLReportGenerator._format_duration(duration)

        user_id_display = user_info.get("user_id", "") or "未知"
        user_name_display = user_info.get("user_name", "") or ""
        user_account_display = user_info.get("user_account", "") or ""
        user_ip_display = user_info.get("user_ip", "") or ""

        status_icon = "✓" if success else "✗"

        # 用户信息行：user_id · IP · user_name · user_account
        user_parts = [user_id_display]
        if user_ip_display:
            user_parts.append(user_ip_display)
        if user_name_display:
            user_parts.append(user_name_display)
        if user_account_display:
            user_parts.append(user_account_display)
        user_line = " · ".join(user_parts)

        # 单步骤块
        if block.get("single_step"):
            step_data = block.get("step_data", {})
            # 补充 method 字段（如果缺失，使用块信息）
            if not step_data.get("method"):
                step_data = dict(step_data)  # 复制避免修改原始数据
                step_data["method"] = method
            step_html = HTMLReportGenerator._render_aw_step(step_data)
            return f'''
        <div class="aw-block {item_class} {expanded_class}">
            <div class="aw-header">
                <div class="aw-icon">{status_icon}</div>
                <div class="aw-info">
                    <div class="aw-title-row">
                        <span class="aw-title">{block_title}</span>
                        <span class="aw-duration">{duration_str}</span>
                    </div>
                    <div class="aw-meta">{user_line} · {time_str}</div>
                </div>
            </div>
            <div class="aw-content">
                <div class="aw-steps">{step_html}</div>
            </div>
        </div>'''

        # 业务方法块（多步骤）
        steps = block.get("steps", [])
        steps_html = ""
        for step in steps:
            steps_html += HTMLReportGenerator._render_aw_step(step)

        # 如果业务方法失败但没有子步骤失败（整体失败），显示错误信息
        if not success and steps:
            business_result = block.get("business_result", {})
            error_msg = business_result.get("error", "")
            error_screenshot = business_result.get("error_screenshot", "")
            if error_msg:
                # 在子步骤前显示业务方法的错误信息
                error_html = f'<div class="aw-step failed"><div class="step-error">{error_msg}</div>'
                if error_screenshot and len(error_screenshot) > 100:
                    error_html += f'''
                    <div class="step-screenshots">
                        <div class="step-screenshot-wrapper">
                            <img src="data:image/png;base64,{error_screenshot}" class="step-screenshot" onclick="showImage('{error_screenshot}')">
                            <div class="step-screenshot-label">失败截图</div>
                        </div>
                    </div>'''
                error_html += '</div>'
                steps_html = error_html + steps_html

        return f'''
    <div class="aw-block {item_class} {expanded_class}">
        <div class="aw-header">
            <div class="aw-icon">{status_icon}</div>
            <div class="aw-info">
                <div class="aw-title-row">
                    <span class="aw-title">{block_title}</span>
                    <span class="aw-duration">{duration_str}</span>
                </div>
                <div class="aw-meta">{user_line} · {time_str}</div>
            </div>
        </div>
        <div class="aw-content">
            <div class="aw-steps">{steps_html}</div>
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
            padding: 24px;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}

        /* 报告头部 */
        .header {{
            background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
            border-radius: 16px;
            padding: 24px 32px;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(34,197,94,0.1);
        }}
        .header.failed {{
            background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
            box-shadow: 0 4px 20px rgba(239,68,68,0.1);
        }}
        .header-content {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }}
        .header-left {{ flex: 1; }}
        .header h1 {{ margin: 0 0 4px 0; font-size: 22px; color: #166534; font-weight: 700; }}
        .header.failed h1 {{ color: #dc2626; }}
        .header h2 {{ margin: 0; font-size: 14px; color: #15803d; font-weight: 400; }}
        .header.failed h2 {{ color: #b91c1c; }}
        .header-right {{ display: flex; align-items: center; gap: 20px; }}
        .status-badge {{
            padding: 10px 20px;
            border-radius: 24px;
            font-weight: 600;
            font-size: 14px;
            box-shadow: 0 2px 10px rgba(34,197,94,0.3);
        }}
        .status-passed {{ background: #22c55e; color: white; }}
        .status-failed {{ background: #ef4444; color: white; box-shadow: 0 2px 10px rgba(239,68,68,0.3); }}
        .header-meta {{ text-align: right; }}
        .header-meta .duration {{ font-size: 20px; font-weight: 700; color: #166534; }}
        .header.failed .header-meta .duration {{ color: #dc2626; }}
        .header-meta .time {{ font-size: 12px; color: #6b7280; margin-top: 2px; }}

        .failed-steps {{
            margin-top: 16px;
            padding: 12px 16px;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #ef4444;
        }}
        .failed-steps-title {{ font-weight: 600; color: #dc2626; margin-bottom: 8px; font-size: 13px; }}
        .failed-steps-list {{ margin: 0; padding-left: 20px; color: #7f1d1d; font-size: 13px; }}
        .failed-steps-list li {{ margin: 4px 0; }}

        .error-box {{
            margin-top: 16px;
            padding: 12px 16px;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #ef4444;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #dc2626;
            white-space: pre-wrap;
            word-break: break-all;
        }}

        .logs-card {{
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.04);
        }}
        .logs-card h3 {{ margin: 0 0 16px 0; font-size: 14px; color: #374151; font-weight: 600; }}

        /* 步骤日志 */
        .log-item {{
            padding: 12px 16px;
            margin: 8px 0;
            background: #f9fafb;
            border-radius: 8px;
        }}
        .log-item:hover {{ background: #f3f4f6; }}
        .log-time {{ color: #9ca3af; font-size: 12px; font-family: 'Consolas', monospace; margin-right: 12px; }}
        .log-type {{
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            margin-right: 8px;
        }}
        .type-step {{ background: #dbeafe; color: #1d4ed8; }}
        .log-name {{ font-weight: 500; color: #374151; font-size: 13px; }}
        .log-detail {{
            margin-top: 8px;
            padding: 8px 12px;
            background: white;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            color: #6b7280;
            white-space: pre-wrap;
            word-break: break-all;
        }}

        /* AW 块容器 */
        .aw-block {{
            margin: 12px 0;
            border-radius: 12px;
            background: white;
            border: 1px solid #e5e7eb;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        .aw-block.success {{ border-color: #bbf7d0; }}
        .aw-block.failed {{ border-color: #fecaca; }}

        /* 卡片头部 */
        .aw-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px;
            cursor: pointer;
            transition: background 0.15s;
        }}
        .aw-block.success .aw-header {{ background: linear-gradient(to right, #f0fdf4, white); }}
        .aw-block.failed .aw-header {{ background: linear-gradient(to right, #fef2f2, white); }}
        .aw-header:hover {{ filter: brightness(0.98); }}

        .aw-icon {{
            width: 36px;
            height: 36px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            flex-shrink: 0;
        }}
        .aw-block.success .aw-icon {{ background: #dcfce7; color: #22c55e; }}
        .aw-block.failed .aw-icon {{ background: #fee2e2; color: #ef4444; }}

        .aw-info {{ flex: 1; min-width: 0; }}
        .aw-title-row {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
        .aw-title {{ font-weight: 600; color: #1f2937; font-size: 14px; }}
        .aw-duration {{
            font-weight: 700;
            font-size: 14px;
        }}
        .aw-block.success .aw-duration {{ color: #166534; }}
        .aw-block.failed .aw-duration {{ color: #dc2626; }}
        .aw-meta {{ color: #6b7280; font-size: 12px; margin-top: 2px; }}

        /* 展开内容 */
        .aw-content {{ display: none; padding: 12px; }}
        .aw-block.expanded .aw-content {{ display: block; }}
        .aw-block.success .aw-content {{ background: #f0fdf4; }}
        .aw-block.failed .aw-content {{ background: #fef2f2; }}

        /* 子步骤 */
        .aw-steps {{ display: flex; flex-direction: column; gap: 6px; }}
        .aw-step {{
            background: white;
            padding: 10px 14px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            transition: box-shadow 0.15s;
        }}
        .aw-step:hover {{ box-shadow: 0 2px 4px rgba(0,0,0,0.08); }}
        .aw-step.failed {{ border: 1px solid #fecaca; }}

        .step-status {{
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
        }}
        .step-status.success {{ background: #dcfce7; color: #166534; }}
        .step-status.failed {{ background: #fee2e2; color: #dc2626; }}

        .step-title {{ flex: 1; color: #374151; font-size: 12px; font-weight: 500; }}
        .step-duration {{ color: #9ca3af; font-size: 11px; }}

        .step-detail {{
            display: none;
            width: 100%;
            margin-top: 8px;
            padding: 10px 12px;
            background: #f9fafb;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            color: #4b5563;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .aw-step.expanded .step-detail {{ display: block; }}

        .step-error {{
            margin-top: 8px;
            padding: 8px 10px;
            background: #fef2f2;
            border-radius: 4px;
            color: #dc2626;
        }}

        .step-screenshots {{
            width: 100%;
            margin-top: 8px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .step-screenshot-wrapper {{ text-align: center; }}
        .step-screenshot {{
            width: 180px;
            height: 120px;
            object-fit: cover;
            border-radius: 6px;
            border: 2px solid #e5e7eb;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .step-screenshot:hover {{ transform: scale(1.02); }}
        .step-screenshot-label {{ margin-top: 4px; font-size: 11px; color: #6b7280; }}

        .screenshots-card {{
            background: white;
            border-radius: 16px;
            padding: 24px;
            margin-top: 24px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.04);
        }}
        .screenshots-card h3 {{ margin: 0 0 16px 0; font-size: 14px; color: #374151; font-weight: 600; }}
        .screenshots-grid {{ display: flex; flex-wrap: wrap; gap: 16px; }}
        .screenshot-item {{ cursor: pointer; text-align: center; }}
        .screenshot-item img {{
            width: 200px;
            height: 130px;
            object-fit: cover;
            border-radius: 8px;
            border: 2px solid #e5e7eb;
        }}
        .screenshot-item .user-id {{ margin-top: 6px; font-size: 12px; color: #6b7280; }}

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

        /* 步骤卡片样式 */
        .step-block {{ border-color: #dbeafe; }}
        .step-block .aw-header {{ background: linear-gradient(to right, #eff6ff, white); }}
        .step-block .aw-icon {{ background: #dbeafe; color: #1d4ed8; }}
        .step-block .aw-content {{ background: #eff6ff; }}
        .step-detail-box {{
            padding: 10px 12px;
            background: white;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            color: #4b5563;
            white-space: pre-wrap;
            word-break: break-all;
        }}

        /* 错误卡片样式 */
        .error-block {{ border-color: #fecaca; }}
        .error-block .aw-content {{ background: #fef2f2; }}
        .error-detail {{
            padding: 10px 12px;
            background: white;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            color: #dc2626;
            white-space: pre-wrap;
            word-break: break-all;
        }}
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
        <div class="logs-card">
            <h3>执行日志</h3>
            {logs_html}
        </div>
        {screenshots_html}
    </div>
    <div id="modal" class="modal" onclick="this.classList.remove('show')">
        <span class="modal-close">&times;</span>
        <img id="modal-img" src="">
    </div>
    <script>
        function showImage(base64) {{
            document.getElementById('modal-img').src = 'data:image/png;base64,' + base64;
            document.getElementById('modal').classList.add('show');
        }}

        // AW 块折叠/展开
        document.querySelectorAll('.aw-header').forEach(header => {{
            header.addEventListener('click', function(e) {{
                if (e.target.closest('.step-detail') || e.target.closest('.step-screenshots')) return;
                const block = this.closest('.aw-block');
                block.classList.toggle('expanded');
            }});
        }});

        // 原子操作步骤折叠/展开
        document.querySelectorAll('.aw-step').forEach(step => {{
            step.addEventListener('click', function(e) {{
                if (e.target.closest('.step-detail') || e.target.closest('.step-screenshots')) return;
                this.classList.toggle('expanded');
            }});
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
        """构建日志列表 HTML，按时间统一排序。"""
        # 构建所有日志项，统一按时间排序
        log_items: List[tuple] = []  # (time_str, html)

        # 使用树形结构构建 AW 块
        aw_blocks = HTMLReportGenerator._build_aw_tree(logs)
        for block in aw_blocks:
            time_str = block.get("time", "")
            html = HTMLReportGenerator._render_aw_block(block)
            log_items.append((time_str, html))

        # 处理其他类型日志（step、error）使用卡片样式
        for log in logs:
            log_type = log.get("type", "")
            time_str = log.get("time", "")

            if log_type == "step":
                step_name = log.get('step', '')
                detail = log.get('detail', '')
                # 只过滤 base64，不截断其他内容
                clean_detail = HTMLReportGenerator._clean_text_for_display(detail) if detail else ""

                html = f"""
            <div class="aw-block step-block">
                <div class="aw-header step-header">
                    <div class="aw-icon step-icon">▶</div>
                    <div class="aw-info">
                        <div class="aw-title-row">
                            <span class="aw-title">{step_name}</span>
                        </div>
                        <div class="aw-meta">{time_str}</div>
                    </div>
                </div>
                {f'<div class="aw-content step-content"><div class="step-detail-box">{clean_detail}</div></div>' if clean_detail else ''}
            </div>"""
                log_items.append((time_str, html))

            # error 类型日志不显示，已在报告头部显示
            # elif log_type == "error":

        # 按时间排序
        log_items.sort(key=lambda x: x[0] or "")

        return "\n".join(item[1] for item in log_items) if log_items else '<div class="aw-block"><div class="aw-header"><span style="color: #868e96;">暂无日志</span></div></div>'

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
                <div class="screenshot-item" onclick="showImage('{base64_data}')">
                    <img src="data:image/png;base64,{base64_data}" alt="{user_id}">
                    <div class="user-id">📷 {user_id}</div>
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