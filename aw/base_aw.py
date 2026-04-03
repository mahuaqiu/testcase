"""AW 基类。"""

import functools
import inspect
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

from common.testagent_client import TestagentClient
from common.report_logger import ReportLogger
from common.parallel import is_collecting, get_action_queue, Action
from common.utils import load_image_as_base64

if TYPE_CHECKING:
    from common.user import User


class AWError(Exception):
    """AW 操作失败异常。"""

    def __init__(self, method: str, result: Dict[str, Any]):
        self.method = method
        self.result = result
        error_msg = result.get("error", "未知错误")
        super().__init__(f"{method} 执行失败: {error_msg}")


def _auto_log_aw_call(func):
    """自动记录业务方法参数的装饰器。

    用于 do_*/should_* 方法，在执行前记录方法参数。
    这样业务方法块标题可以显示关键参数。
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # 获取方法签名和绑定参数
        sig = inspect.signature(func)
        bound_args = sig.bind(self, *args, **kwargs)
        bound_args.apply_defaults()

        # 提取参数（排除 self）
        method_args = {
            k: v for k, v in bound_args.arguments.items()
            if k != "self"
        }

        # 获取 parent_aw（调用栈中上层的业务方法）
        parent_aw = self._find_parent_aw(skip_self=True)

        # 非收集模式下，记录业务方法参数
        if not is_collecting():
            logger = ReportLogger.get_current()
            logger.log_aw_call(
                aw_name=self._aw_name,
                method=func.__name__,
                args=method_args,
                success=True,  # 先假设成功，失败时更新
                result={},
                duration_ms=0,  # 先记0，实际耗时由子步骤计算
                parent_aw=parent_aw,
                is_business_method=True,  # 标记为业务方法日志
            )

        # 执行原方法
        return func(self, *args, **kwargs)

    return wrapper


class BaseAW:
    """AW 基类。

    所有 AW 类继承此类，提供 client 和 user 的访问。
    自动记录日志并检查执行结果，失败时抛出 AWError。

    Args:
        client: TestagentClient 实例。
        user: User 实例（可选），用于获取账号密码等信息。
    """

    PLATFORM: str = ""  # 子类必须覆盖

    def __init_subclass__(cls, **kwargs):
        """子类创建时自动装饰所有 do_*/should_* 方法。"""
        super().__init_subclass__(**kwargs)
        for name in dir(cls):
            if name.startswith(('do_', 'should_')):
                method = getattr(cls, name)
                if callable(method) and not hasattr(method, '_auto_logged'):
                    # 装饰并替换类方法
                    wrapped = _auto_log_aw_call(method)
                    wrapped._auto_logged = True
                    setattr(cls, name, wrapped)

    def __init__(self, client: TestagentClient, user: Optional["User"] = None):
        self.client = client
        self.user = user
        self._aw_name = self.__class__.__name__

    # ── 内部方法 ─────────────────────────────────────────

    def _find_parent_aw(self, skip_self: bool = False) -> str:
        """从调用栈中查找最近的 do_*/should_* 方法作为 parent。

        Args:
            skip_self: 是否跳过当前方法（装饰器调用时需要）。

        Returns:
            父级 AW 标识，如 "LoginAW.do_login"。
            如果没找到业务方法，返回空字符串（顶层）。
        """
        stack = inspect.stack()
        aw_name = self._aw_name

        try:
            first = True
            for frame_info in stack:
                func_name = frame_info.function
                # 跳过当前方法（装饰器调用时）
                if skip_self and first:
                    first = False
                    continue
                if func_name.startswith(('do_', 'should_')):
                    return f"{aw_name}.{func_name}"
            return ""
        finally:
            del stack  # 显式释放栈帧引用

    def _execute_with_log(
        self,
        method: str,
        action_data: Dict[str, Any],
        log_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行操作并记录日志，失败时抛出异常。

        在 parallel() 上下文中收集 action_data，否则立即执行。

        Args:
            method: 方法名。
            action_data: 原始 action 数据（发给服务端）。
            log_args: 用于日志记录的参数。

        Returns:
            执行结果（收集模式下返回空字典）。

        Raises:
            AWError: 执行失败时抛出。
        """
        # 检查是否处于收集模式（parallel 上下文）
        if is_collecting():
            queue = get_action_queue()
            if queue is not None:
                # 构建 Action 对象并添加到队列
                user_id = self.user.user_id if self.user else ""
                action_obj = Action(
                    action_data=action_data,
                    platform=self.PLATFORM,
                    user_id=user_id,
                    aw_name=self._aw_name,
                    method=method,
                    log_args=log_args,
                    client=self.client,
                )
                queue.append(action_obj)
                return {}  # 收集模式返回空字典

        # 同步执行模式
        # 自动识别 parent_aw
        parent_aw = self._find_parent_aw()
        logger = ReportLogger.get_current()
        start_time = time.time()

        try:
            # 调用 client.execute（批量接口，传入单个 action）
            result = self.client.execute(self.PLATFORM, [action_data])
        except Exception as e:
            # 记录异常
            duration_ms = int((time.time() - start_time) * 1000)
            logger.log_aw_call(
                aw_name=self._aw_name,
                method=method,
                args=log_args,
                success=False,
                result={"error": str(e)},
                duration_ms=duration_ms,
                parent_aw=parent_aw,
            )
            raise

        duration_ms = int((time.time() - start_time) * 1000)

        # 从 actions 列表中取第一个结果
        action_result = result.get("actions", [{}])[0] if result.get("actions") else {}
        success = action_result.get("status") == "success"

        # 失败时立即截图，并读取目标图片（仅 image_* 操作）
        target_image_base64 = ""
        target_image_path = ""
        if not success:
            # 立即截图当前屏幕
            error_screenshot = self.screenshot()
            if error_screenshot:
                action_result["error_screenshot"] = error_screenshot

            # image_* 操作失败时，读取目标图片
            if method.startswith("image_") and "image_path" in log_args:
                target_image_path = log_args["image_path"]
                target_image_base64 = self._load_image_as_base64(target_image_path) or ""

        # 记录 AW 调用日志
        user_id = self.user.user_id if self.user else ""
        user_account = self.user.account if self.user else ""
        user_name = self.user.name if self.user else ""

        # 构建完整的 result（包含 status/duration_ms/output/error）
        full_result = {
            "status": action_result.get("status", "failed"),
            "platform": self.PLATFORM,
            "duration_ms": action_result.get("duration_ms", 0),
            "actions": [action_result],
            "output": action_result.get("output", ""),
            "error": action_result.get("error", ""),
        }
        if "error_screenshot" in action_result:
            full_result["error_screenshot"] = action_result["error_screenshot"]

        logger.log_aw_call(
            aw_name=self._aw_name,
            method=method,
            args={"user_id": user_id, "user_account": user_account, "user_name": user_name, **log_args},
            success=success,
            result=full_result,
            duration_ms=duration_ms,
            target_image=target_image_base64,
            target_image_path=target_image_path,
            parent_aw=parent_aw,
        )

        # 记录 worker 调用日志（用于调试，报告中不显示）
        logger.log_worker_call(
            api="task/execute",
            params={"platform": self.PLATFORM, "method": method, "user_id": user_id, "user_account": user_account, "user_name": user_name, **log_args},
            success=success,
            response=full_result,
            duration_ms=duration_ms,
        )

        # 失败时抛出异常
        if not success:
            raise AWError(f"{self._aw_name}.{method}", full_result)

        return full_result

    # ── OCR 动作 ─────────────────────────────────────────

    def ocr_click(self, text: str, **kwargs) -> dict:
        """OCR 识别并点击。

        Args:
            text: 要识别并点击的文字。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        action_data = {
            "action_type": "ocr_click",
            "value": text,
            "timeout": kwargs.get("timeout", 5) * 1000,
            "index": kwargs.get("index", 0),
        }
        if "offset" in kwargs:
            action_data["offset"] = kwargs["offset"]

        return self._execute_with_log("ocr_click", action_data, {"text": text, **kwargs})

    def ocr_input(self, label: str, content: str, **kwargs) -> dict:
        """OCR 定位后输入。

        Args:
            label: 要定位的文字标签。
            content: 要输入的内容。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 输入偏移量 {"x": 0, "y": 0}。
        """
        action_data = {
            "action_type": "ocr_input",
            "value": label,
            "text": content,
            "timeout": kwargs.get("timeout", 5) * 1000,
            "index": kwargs.get("index", 0),
        }
        if "offset" in kwargs:
            action_data["offset"] = kwargs["offset"]

        return self._execute_with_log("ocr_input", action_data, {"label": label, "content": content, **kwargs})

    def ocr_wait(self, text: str, **kwargs) -> dict:
        """等待文字出现。

        Args:
            text: 要等待的文字。
            timeout: 超时时间（秒），默认 5。
        """
        action_data = {
            "action_type": "ocr_wait",
            "value": text,
            "timeout": kwargs.get("timeout", 5) * 1000,
        }

        return self._execute_with_log("ocr_wait", action_data, {"text": text, **kwargs})

    def ocr_assert(self, text: str, **kwargs) -> dict:
        """断言文字存在。

        Args:
            text: 要断言的文字。
            timeout: 超时时间（秒），默认 5。
        """
        action_data = {
            "action_type": "ocr_assert",
            "value": text,
            "timeout": kwargs.get("timeout", 5) * 1000,
        }

        return self._execute_with_log("ocr_assert", action_data, {"text": text, **kwargs})

    def ocr_get_text(self, **kwargs) -> str:
        """获取屏幕所有文字。

        Returns:
            识别到的文字内容。
        """
        action_data = {
            "action_type": "ocr_get_text",
            "value": "",
            "timeout": kwargs.get("timeout", 5) * 1000,
        }

        result = self._execute_with_log("ocr_get_text", action_data, {**kwargs})
        # 从结果中提取文字
        if result.get("actions"):
            return result["actions"][0].get("output", "")
        return ""

    def ocr_paste(self, text: str, content: str, **kwargs) -> dict:
        """OCR 定位后粘贴剪贴板内容。

        Args:
            text: 要定位的文字。
            content: 剪贴板内容。
            timeout: 超时时间（秒），默认 5。
        """
        action_data = {
            "action_type": "ocr_paste",
            "value": text,
            "text": content,
            "timeout": kwargs.get("timeout", 5) * 1000,
        }

        return self._execute_with_log("ocr_paste", action_data, {"text": text, "content": content, **kwargs})

    def ocr_move(self, text: str, **kwargs) -> dict:
        """OCR 定位后移动鼠标（仅桌面端支持）。

        Args:
            text: 要定位的文字。
            timeout: 超时时间（秒），默认 5。
        """
        action_data = {
            "action_type": "ocr_move",
            "value": text,
            "timeout": kwargs.get("timeout", 5) * 1000,
        }

        return self._execute_with_log("ocr_move", action_data, {"text": text, **kwargs})

    # ── 图像识别动作 ─────────────────────────────────────────

    def _load_image_as_base64(self, image_path: str) -> Optional[str]:
        """将本地图片转换为 base64 编码。

        Args:
            image_path: 图片路径（相对或绝对）。

        Returns:
            base64 编码的图片内容，如果文件不存在则返回 None。
        """
        return load_image_as_base64(image_path)

    def image_click(self, image_path: str, **kwargs) -> dict:
        """图像识别点击。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        action_data = {
            "action_type": "image_click",
            "image_base64": image_base64,
            "timeout": kwargs.get("timeout", 5) * 1000,
            "threshold": kwargs.get("confidence", 0.8),
        }

        return self._execute_with_log("image_click", action_data, {"image_path": image_path, **kwargs})

    def image_wait(self, image_path: str, **kwargs) -> dict:
        """等待图像出现。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        action_data = {
            "action_type": "image_wait",
            "image_base64": image_base64,
            "timeout": kwargs.get("timeout", 5) * 1000,
            "threshold": kwargs.get("confidence", 0.8),
        }

        return self._execute_with_log("image_wait", action_data, {"image_path": image_path, **kwargs})

    def image_assert(self, image_path: str, **kwargs) -> dict:
        """断言图像存在。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        action_data = {
            "action_type": "image_assert",
            "image_base64": image_base64,
            "timeout": kwargs.get("timeout", 5) * 1000,
            "threshold": kwargs.get("confidence", 0.8),
        }

        return self._execute_with_log("image_assert", action_data, {"image_path": image_path, **kwargs})

    def image_click_near_text(self, image_path: str, text: str, **kwargs) -> dict:
        """点击文本附近最近的图像。

        Args:
            image_path: 图片路径。
            text: 文本内容。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        action_data = {
            "action_type": "image_click_near_text",
            "image_base64": image_base64,
            "value": text,
            "end_x": kwargs.get("max_distance", 500),
            "timeout": kwargs.get("timeout", 5) * 1000,
            "threshold": kwargs.get("confidence", 0.8),
        }

        return self._execute_with_log("image_click_near_text", action_data, {"image_path": image_path, "text": text, **kwargs})

    def image_move(self, image_path: str, **kwargs) -> dict:
        """图像识别后移动鼠标（仅桌面端支持）。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        action_data = {
            "action_type": "image_move",
            "image_base64": image_base64,
            "timeout": kwargs.get("timeout", 5) * 1000,
            "threshold": kwargs.get("confidence", 0.8),
        }

        return self._execute_with_log("image_move", action_data, {"image_path": image_path, **kwargs})

    # ── 坐标动作 ─────────────────────────────────────────

    def click(self, x: int, y: int) -> dict:
        """坐标点击。

        Args:
            x: X 坐标。
            y: Y 坐标。
        """
        action_data = {
            "action_type": "click",
            "x": x,
            "y": y,
        }

        return self._execute_with_log("click", action_data, {"x": x, "y": y})

    def move(self, x: int, y: int, **kwargs) -> dict:
        """移动鼠标到指定坐标（仅桌面端支持）。

        Args:
            x: X 坐标。
            y: Y 坐标。
        """
        action_data = {
            "action_type": "move",
            "x": x,
            "y": y,
        }

        return self._execute_with_log("move", action_data, {"x": x, "y": y, **kwargs})

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, **kwargs) -> dict:
        """滑动操作。

        Args:
            from_x: 起点 X 坐标。
            from_y: 起点 Y 坐标。
            to_x: 终点 X 坐标。
            to_y: 终点 Y 坐标。
            duration: 滑动持续时间（毫秒）。
        """
        action_data = {
            "action_type": "swipe",
            "from": {"x": from_x, "y": from_y},
            "to": {"x": to_x, "y": to_y},
        }
        if "duration" in kwargs:
            action_data["duration"] = kwargs["duration"]

        return self._execute_with_log("swipe", action_data, {"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y, **kwargs})

    def input_text(self, x: int, y: int, text: str) -> dict:
        """在指定坐标输入文本。

        Args:
            x: X 坐标。
            y: Y 坐标。
            text: 要输入的文本。
        """
        action_data = {
            "action_type": "input",
            "x": x,
            "y": y,
            "text": text,
        }

        return self._execute_with_log("input_text", action_data, {"x": x, "y": y, "text": text})

    # ── 其他动作 ─────────────────────────────────────────

    def press(self, key: str) -> dict:
        """按键操作。

        Args:
            key: 按键名称（如 "Enter", "Tab", "Escape"）。
        """
        action_data = {
            "action_type": "press",
            "key": key,
        }

        return self._execute_with_log("press", action_data, {"key": key})

    def wait(self, duration: float) -> dict:
        """固定等待。

        Args:
            duration: 等待时间（秒），与 time.sleep() 单位一致。
        """
        duration_ms = int(duration * 1000)
        action_data = {
            "action_type": "wait",
            "value": str(duration_ms),
        }

        return self._execute_with_log("wait", action_data, {"duration_ms": duration_ms})

    def start_app(self, app_id: str) -> dict:
        """启动应用。

        Args:
            app_id: 应用 ID 或名称。
        """
        action_data = {
            "action_type": "start_app",
            "value": app_id,
        }

        return self._execute_with_log("start_app", action_data, {"app_id": app_id})

    def stop_app(self, app_id: str) -> dict:
        """关闭应用。

        Args:
            app_id: 应用 ID 或名称。
        """
        action_data = {
            "action_type": "stop_app",
            "value": app_id,
        }

        return self._execute_with_log("stop_app", action_data, {"app_id": app_id})

    def navigate(self, url: str) -> dict:
        """导航到 URL（Web 端专用）。

        Args:
            url: 目标 URL。
        """
        action_data = {
            "action_type": "navigate",
            "value": url,
        }

        return self._execute_with_log("navigate", action_data, {"url": url})

    def screenshot(self) -> str:
        """截图并返回 base64。

        Returns:
            截图的 base64 编码，失败返回空字符串。
        """
        result = self.client.screenshot(self.PLATFORM)
        if result.get("status") == "success" and result.get("actions"):
            action = result["actions"][0]
            # 优先取 screenshot 字段，其次取 output 字段
            return action.get("screenshot") or action.get("output", "")
        return ""