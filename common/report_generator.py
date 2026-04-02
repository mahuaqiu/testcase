"""HTML 报告生成器。"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


class HTMLReportGenerator:
    """HTML 报告生成器。"""

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
                            if ak == "screenshot" and isinstance(av, str) and len(av) > 100:
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
            "duration_ms", "timeout", "index", "confidence"
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
            if isinstance(v, str):
                parts.append(f'{k}="{v}"')
            else:
                parts.append(f"{k}={v}")

        return f"{aw_name}.{method}({', '.join(parts)})"

    @staticmethod
    def _build_aw_tree(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将日志按 parent_aw 分组构建树形结构。

        Args:
            logs: 原始日志列表。

        Returns:
            块列表，每个块包含业务方法信息和子步骤列表。
        """
        # 按 parent_aw 分组
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for log in logs:
            if log.get("type") != "aw_call":
                continue
            parent = log.get("parent_aw", "")
            if parent not in groups:
                groups[parent] = []
            groups[parent].append(log)

        # 构建业务方法块（parent_aw != "" 的日志属于某个业务方法）
        # 首先找出所有业务方法块
        business_blocks: Dict[str, Dict[str, Any]] = {}

        for parent_aw, steps in groups.items():
            if parent_aw == "":
                continue  # 顶层原子操作，后面处理

            # 从 parent_aw 解析 aw_name 和 method
            parts = parent_aw.rsplit(".", 1)
            if len(parts) != 2:
                continue
            aw_name, method = parts

            # 计算整体状态和耗时
            total_duration = sum(s.get("duration_ms", 0) for s in steps)
            all_success = all(s.get("success", True) for s in steps)

            # 从第一个步骤获取用户信息
            first_step = steps[0] if steps else {}
            args = first_step.get("args", {})
            user_info = {
                "user_id": args.get("user_id", ""),
                "user_name": args.get("user_name", ""),
                "user_account": args.get("user_account", ""),
            }

            business_blocks[parent_aw] = {
                "block_id": parent_aw,
                "aw_name": aw_name,
                "method": method,
                "user_info": user_info,
                "success": all_success,
                "duration_ms": total_duration,
                "steps": steps,
                "time": first_step.get("time", ""),
            }

        # 构建顶层块列表（parent_aw == "" 的原子操作 + 业务方法块）
        top_blocks: List[Dict[str, Any]] = []

        # 添加顶层原子操作（不属于任何业务方法）
        for log in groups.get("", []):
            aw_name = log.get("aw_name", "")
            method = log.get("method", "")
            block_id = f"{aw_name}.{method}"

            args = log.get("args", {})
            user_info = {
                "user_id": args.get("user_id", ""),
                "user_name": args.get("user_name", ""),
                "user_account": args.get("user_account", ""),
            }

            top_blocks.append({
                "block_id": block_id,
                "aw_name": aw_name,
                "method": method,
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
    def _render_aw_step(step: Dict[str, Any]) -> str:
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

        # 清理参数和结果用于详情显示
        clean_args = {k: v for k, v in args.items() if k not in ("user_id", "user_account", "user_name")}
        clean_result = HTMLReportGenerator._clean_response_for_display(step.get("result", {}))

        detail_parts = []
        if clean_args:
            detail_parts.append(f"参数: {clean_args}")
        detail_parts.append(f"结果: {clean_result}")
        detail_html = "<br>".join(detail_parts)

        # 失败时展示截图
        screenshots_html = ""
        if not success:
            result = step.get("result", {})
            error_screenshot = result.get("error_screenshot", "")
            target_image = step.get("target_image", "")

            screenshot_imgs = []
            if error_screenshot and len(error_screenshot) > 100:
                screenshot_imgs.append(f'''
                <div class="step-screenshot-wrapper">
                    <img src="data:image/png;base64,{error_screenshot}" class="step-screenshot" onclick="showImage('{error_screenshot}')">
                    <div class="step-screenshot-label">📸 当前屏幕</div>
                </div>''')
            if target_image and len(target_image) > 100:
                screenshot_imgs.append(f'''
                <div class="step-screenshot-wrapper">
                    <img src="data:image/png;base64,{target_image}" class="step-screenshot" onclick="showImage('{target_image}')">
                    <div class="step-screenshot-label">🎯 目标图片</div>
                </div>''')

            if screenshot_imgs:
                screenshots_html = f'<div class="step-screenshots">{"".join(screenshot_imgs)}</div>'

        return f'''
        <div class="aw-step">
            <span class="step-arrow">▶</span>
            <span class="step-title">{step_title}</span>
            <span class="step-status {status_class}">{status_text}</span>
            <span class="step-duration">{duration}ms</span>
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
        expanded_class = "expanded" if not success else ""  # 失败块默认展开

        aw_name = block.get("aw_name", "")
        method = block.get("method", "")
        user_info = block.get("user_info", {})
        duration = block.get("duration_ms", 0)
        time_str = block.get("time", "")

        # 格式化标题
        block_title = f"{aw_name}.{method}()"

        # 格式化用户信息
        user_id_display = user_info.get("user_id", "") or "未知"
        user_name_display = user_info.get("user_name", "") or ""
        user_account_display = user_info.get("user_account", "") or ""

        # 单步骤块（顶层原子操作）
        if block.get("single_step"):
            step_data = block.get("step_data", {})
            step_html = HTMLReportGenerator._render_aw_step(step_data)
            return f'''
        <div class="aw-block {item_class} {expanded_class}">
            <div class="aw-header">
                <span class="aw-arrow">▶</span>
                <span class="log-time">{time_str}</span>
                <div class="log-type-wrapper">
                    <span class="log-type type-aw_call">AW</span>
                    <span class="log-user-id">{user_id_display}</span>
                    <span class="log-user-name">{user_name_display}</span>
                    <span class="log-user-account">{user_account_display}</span>
                </div>
                <span class="aw-title">{block_title}</span>
                <span class="aw-status {item_class}">{"✓" if success else "✗"}</span>
                <span class="aw-duration">{duration}ms</span>
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

        status_text = "成功" if success else "失败"

        return f'''
    <div class="aw-block {item_class} {expanded_class}">
        <div class="aw-header">
            <span class="aw-arrow">▶</span>
            <span class="log-time">{time_str}</span>
            <div class="log-type-wrapper">
                <span class="log-type type-aw_call">AW</span>
                <span class="log-user-id">{user_id_display}</span>
                <span class="log-user-name">{user_name_display}</span>
                <span class="log-user-account">{user_account_display}</span>
            </div>
            <span class="aw-title">{block_title}</span>
            <span class="aw-status {item_class}">{status_text}</span>
            <span class="aw-duration">{duration}ms</span>
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{
            background: white;
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        .header h1 {{ margin: 0 0 8px 0; font-size: 28px; color: #1a1a2e; }}
        .header h2 {{ margin: 0 0 20px 0; font-size: 16px; font-weight: normal; color: #6c757d; }}
        .header-meta {{ display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }}
        .status-badge {{ padding: 8px 20px; border-radius: 20px; font-weight: 600; font-size: 14px; }}
        .status-passed {{ background: #d4edda; color: #155724; }}
        .status-failed {{ background: #f8d7da; color: #721c24; }}
        .meta-item {{ color: #6c757d; font-size: 14px; }}
        .meta-item span {{ font-weight: 600; color: #343a40; }}
        .failed-steps {{
            margin-top: 20px;
            padding: 16px 20px;
            background: #fff5f5;
            border-radius: 8px;
            border-left: 4px solid #dc3545;
        }}
        .failed-steps-title {{ font-weight: 600; color: #dc3545; margin-bottom: 10px; font-size: 14px; }}
        .failed-steps-list {{ margin: 0; padding-left: 20px; color: #721c24; }}
        .failed-steps-list li {{ margin: 6px 0; font-size: 14px; }}
        .error-box {{
            background: #fff5f5;
            border-left: 4px solid #f44336;
            padding: 16px;
            margin-top: 20px;
            border-radius: 0 8px 8px 0;
            font-family: 'Consolas', monospace;
            font-size: 13px;
            color: #c62828;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .logs-card {{
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        .logs-card h3 {{ margin: 0 0 20px 0; font-size: 18px; color: #343a40; padding-bottom: 12px; border-bottom: 2px solid #f0f0f0; }}
        .log-item {{
            display: flex;
            align-items: flex-start;
            padding: 12px 16px;
            margin: 8px 0;
            border-radius: 8px;
            transition: background 0.2s;
        }}
        .log-item:hover {{ background: #f8f9fa; }}
        .log-item.success {{ background: #d4edda; border-left: 4px solid #28a745; }}
        .log-item.failed {{ background: #f8d7da; border-left: 4px solid #dc3545; }}
        .log-item.success:hover {{ background: #c3e6cb; }}
        .log-item.failed:hover {{ background: #f5c6cb; }}
        .log-time {{ color: #868e96; font-size: 12px; min-width: 90px; font-family: 'Consolas', monospace; }}
        .log-type {{
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            margin: 0 12px;
        }}
        .type-step {{ background: #e3f2fd; color: #1565c0; }}
        .type-aw_call {{ background: #f3e5f5; color: #7b1fa2; }}
        .type-worker_call {{ background: #e8f5e9; color: #2e7d32; }}
        .type-error {{ background: #ffebee; color: #c62828; }}
        .type-screenshot {{ background: #fff3e0; color: #e65100; }}
        .log-type-wrapper {{
            display: flex;
            flex-direction: column;
            align-items: center;
            margin: 0 12px;
            min-width: 80px;
        }}
        .log-user-id {{
            color: #2e7d32;
            font-size: 11px;
            font-weight: 600;
            margin-top: 4px;
        }}
        .log-user-name {{
            color: #343a40;
            font-size: 10px;
            margin-top: 2px;
        }}
        .log-user-account {{
            color: #6c757d;
            font-size: 10px;
            margin-top: 2px;
        }}
        .log-content {{ flex: 1; }}
        .log-main {{ display: flex; align-items: center; gap: 12px; }}
        .log-name {{ font-weight: 500; color: #343a40; }}
        .log-status {{ font-size: 12px; padding: 2px 8px; border-radius: 4px; }}
        .log-status.success {{ background: #28a745; color: white; }}
        .log-status.failed {{ background: #dc3545; color: white; }}
        .log-duration {{ color: #868e96; font-size: 12px; }}
        .log-detail {{
            margin-top: 8px;
            padding: 10px 12px;
            background: #f8f9fa;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #495057;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .step-screenshots {{
            margin-top: 10px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .step-screenshot-wrapper {{
            text-align: center;
        }}
        .step-screenshot {{
            width: 200px;
            height: 130px;
            object-fit: cover;
            border-radius: 6px;
            border: 2px solid #e9ecef;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .step-screenshot:hover {{ transform: scale(1.05); }}
        .step-screenshot-label {{
            margin-top: 4px;
            font-size: 12px;
            color: #6c757d;
            font-weight: 500;
        }}
        .screenshots-card {{
            background: white;
            border-radius: 16px;
            padding: 24px;
            margin-top: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        .screenshots-card h3 {{ margin: 0 0 20px 0; font-size: 18px; color: #343a40; padding-bottom: 12px; border-bottom: 2px solid #f0f0f0; }}
        .screenshots-grid {{ display: flex; flex-wrap: wrap; gap: 16px; }}
        .screenshot-item {{ cursor: pointer; text-align: center; transition: transform 0.2s; }}
        .screenshot-item:hover {{ transform: scale(1.02); }}
        .screenshot-item img {{
            width: 240px;
            height: 160px;
            object-fit: cover;
            border-radius: 8px;
            border: 2px solid #e9ecef;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        .screenshot-item .user-id {{ margin-top: 8px; font-size: 12px; color: #6c757d; font-weight: 500; }}
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            cursor: zoom-out;
        }}
        .modal.show {{ display: flex; align-items: center; justify-content: center; }}
        .modal img {{
            max-width: 95%;
            max-height: 95%;
            border-radius: 8px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }}
        .modal-close {{ position: fixed; top: 20px; right: 30px; color: white; font-size: 40px; cursor: pointer; }}

        /* AW 块容器 */
        .aw-block {{
            margin: 8px 0;
            border-radius: 8px;
            background: white;
            border: 1px solid #e9ecef;
            transition: all 0.2s;
        }}
        .aw-block:hover {{ background: #f8f9fa; }}
        .aw-block.failed {{
            border-left: 4px solid #dc3545;
            background: #fff5f5;
        }}
        .aw-block.success {{ border-left: 4px solid #28a745; }}

        /* 折叠标题 */
        .aw-header {{
            display: flex;
            align-items: center;
            padding: 12px 16px;
            cursor: pointer;
            gap: 12px;
        }}
        .aw-arrow {{
            color: #6c757d;
            font-size: 12px;
            transition: transform 0.2s;
        }}
        .aw-block.expanded .aw-arrow {{ transform: rotate(90deg); }}
        .aw-title {{
            font-weight: 500;
            color: #343a40;
            flex: 1;
        }}
        .aw-status {{
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
        }}
        .aw-status.success {{ background: #28a745; color: white; }}
        .aw-status.failed {{ background: #dc3545; color: white; }}
        .aw-duration {{ color: #868e96; font-size: 12px; }}

        /* 展开内容 */
        .aw-content {{
            display: none;
            padding: 12px 16px;
            border-top: 1px solid #e9ecef;
        }}
        .aw-block.expanded .aw-content {{ display: block; }}
        .aw-detail {{
            background: #f8f9fa;
            padding: 10px 12px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            white-space: pre-wrap;
            word-break: break-all;
        }}

        /* 子步骤容器 */
        .aw-steps {{
            padding: 0 16px 12px 16px;
        }}

        /* 原子操作步骤 */
        .aw-step {{
            display: flex;
            align-items: center;
            padding: 8px 12px;
            margin: 4px 0;
            background: #f8f9fa;
            border-radius: 6px;
            cursor: pointer;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .aw-step:hover {{ background: #e9ecef; }}

        .step-arrow {{
            color: #6c757d;
            font-size: 10px;
            transition: transform 0.2s;
        }}
        .aw-step.expanded .step-arrow {{ transform: rotate(90deg); }}

        .step-title {{
            font-weight: 500;
            color: #343a40;
            flex: 1;
        }}

        .step-status {{
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
        }}
        .step-status.success {{ background: #28a745; color: white; }}
        .step-status.failed {{ background: #dc3545; color: white; }}

        .step-duration {{
            color: #868e96;
            font-size: 11px;
        }}

        /* 步骤详情 */
        .step-detail {{
            display: none;
            width: 100%;
            margin-top: 8px;
            padding: 8px 12px;
            background: #fff;
            border-radius: 4px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .aw-step.expanded .step-detail {{ display: block; }}

        /* 步骤截图 */
        .step-screenshots {{
            width: 100%;
            margin-top: 8px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{case_name}</h1>
            {f'<h2>{case_title}</h2>' if case_title else ''}
            <div class="header-meta">
                <span class="status-badge {'status-passed' if status == 'passed' else 'status-failed'}">
                    {'✓ 通过' if status == 'passed' else '✗ 失败'}
                </span>
                <span class="meta-item">耗时: <span>{duration_ms}ms</span></span>
                <span class="meta-item">时间: <span>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span></span>
            </div>
            {failed_steps_html}
            {f'<div class="error-box">{error_msg}</div>' if error_msg else ''}
        </div>
        <div class="logs-card">
            <h3>📋 执行日志</h3>
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
            header.addEventListener('click', function() {{
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
        """构建日志列表 HTML。"""
        items = []

        for log in logs:
            log_type = log.get("type", "")
            time_str = log.get("time", "")

            if log_type == "step":
                items.append(f"""
            <div class="log-item">
                <span class="log-time">{time_str}</span>
                <span class="log-type type-step">步骤</span>
                <div class="log-content">
                    <div class="log-main">
                        <span class="log-name">{log.get('step', '')}</span>
                    </div>
                    {f'<div class="log-detail">{log.get("detail", "")}</div>' if log.get('detail') else ''}
                </div>
            </div>""")

            elif log_type == "aw_call":
                success = log.get("success", False)
                item_class = "success" if success else "failed"
                status_class = "success" if success else "failed"
                status_text = "成功" if success else "失败"

                # 失败块默认展开
                expanded_class = "expanded" if not success else ""

                # 格式化用户信息
                args = log.get("args", {})
                user_id = args.get("user_id", "")
                user_account = args.get("user_account", "")
                user_name = args.get("user_name", "")
                user_id_display = user_id if user_id else "未知"
                user_name_display = user_name if user_name else ""
                user_account_display = user_account if user_account else ""

                # 格式化标题（带关键参数）
                aw_title = HTMLReportGenerator._format_aw_title(
                    log.get("aw_name", ""),
                    log.get("method", ""),
                    args
                )

                # 清理参数用于详情显示
                clean_args = {k: v for k, v in args.items() if k not in ("user_id", "user_account", "user_name")}
                clean_result = HTMLReportGenerator._clean_response_for_display(log.get("result", {}))

                # 构建参数和结果详情
                detail_parts = []
                if clean_args:
                    detail_parts.append(f"参数: {clean_args}")
                detail_parts.append(f"结果: {clean_result}")
                detail_html = "<br>".join(detail_parts)

                # 失败时展示截图
                screenshots_html = ""
                if not success:
                    result = log.get("result", {})
                    error_screenshot = result.get("error_screenshot", "")
                    target_image = log.get("target_image", "")

                    screenshot_imgs = []
                    if error_screenshot and len(error_screenshot) > 100:
                        screenshot_imgs.append(f'''
                            <div class="step-screenshot-wrapper">
                                <img src="data:image/png;base64,{error_screenshot}" class="step-screenshot" onclick="showImage('{error_screenshot}')">
                                <div class="step-screenshot-label">📸 当前屏幕</div>
                            </div>''')
                    if target_image and len(target_image) > 100:
                        screenshot_imgs.append(f'''
                            <div class="step-screenshot-wrapper">
                                <img src="data:image/png;base64,{target_image}" class="step-screenshot" onclick="showImage('{target_image}')">
                                <div class="step-screenshot-label">🎯 目标图片</div>
                            </div>''')

                    if screenshot_imgs:
                        screenshots_html = f'<div class="aw-screenshots" style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 12px;">{"".join(screenshot_imgs)}</div>'

                items.append(f"""
            <div class="aw-block {item_class} {expanded_class}">
                <div class="aw-header">
                    <span class="aw-arrow">▶</span>
                    <span class="log-time">{time_str}</span>
                    <div class="log-type-wrapper">
                        <span class="log-type type-aw_call">AW</span>
                        <span class="log-user-id">{user_id_display}</span>
                        <span class="log-user-name">{user_name_display}</span>
                        <span class="log-user-account">{user_account_display}</span>
                    </div>
                    <span class="aw-title">{aw_title}</span>
                    <span class="aw-status {status_class}">{status_text}</span>
                    <span class="aw-duration">{log.get('duration_ms', 0)}ms</span>
                </div>
                <div class="aw-content">
                    <div class="aw-detail">{detail_html}</div>
                    {screenshots_html}
                </div>
            </div>""")

            elif log_type == "worker_call":
                # Worker 调用日志不再单独显示，避免与 AW 日志重复
                # 但仍用于底部截图过滤逻辑
                pass

            elif log_type == "error":
                items.append(f"""
            <div class="log-item failed">
                <span class="log-time">{time_str}</span>
                <span class="log-type type-error">错误</span>
                <div class="log-content">
                    <div class="log-main">
                        <span class="log-name" style="color: #dc3545;">{log.get('error', '')}</span>
                    </div>
                </div>
            </div>""")

        return "\n".join(items) if items else '<div class="log-item"><span style="color: #868e96;">暂无日志</span></div>'

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