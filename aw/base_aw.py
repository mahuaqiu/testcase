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
        # 公共 AW 继承 User 的平台
        platform = self.PLATFORM
        if platform == "common" and self.user:
            platform = self.user.platform

        # 检查是否处于收集模式（parallel 上下文）
        if is_collecting():
            queue = get_action_queue()
            if queue is not None:
                # 构建 Action 对象并添加到队列
                user_id = self.user.user_id if self.user else ""
                # 获取 parent_aw（用于日志聚合）
                parent_aw = self._find_parent_aw()
                action_obj = Action(
                    action_data=action_data,
                    platform=platform,
                    user_id=user_id,
                    aw_name=self._aw_name,
                    method=method,
                    log_args=log_args,
                    client=self.client,
                    parent_aw=parent_aw,  # 传递 parent_aw 以支持日志聚合
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
            result = self.client.execute(platform, [action_data])
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
            "platform": platform,
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
            params={"platform": platform, "method": method, "user_id": user_id, "user_account": user_account, "user_name": user_name, **log_args},
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
        return self._exec("ocr_click",
            {"value": text, **self._ocr_params(kwargs)},
            {"text": text, **kwargs})

    def ocr_input(self, label: str, content: str, **kwargs) -> dict:
        """OCR 定位后输入。

        Args:
            label: 要定位的文字标签。
            content: 要输入的内容。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 输入偏移量 {"x": 0, "y": 0}。
        """
        return self._exec("ocr_input",
            {"value": label, "text": content, **self._ocr_params(kwargs)},
            {"label": label, "content": content, **kwargs})

    def ocr_wait(self, text: str, **kwargs) -> dict:
        """等待文字出现。

        Args:
            text: 要等待的文字。
            timeout: 超时时间（秒），默认 5。
        """
        return self._exec("ocr_wait",
            {"value": text, "timeout": kwargs.get("timeout", 5) * 1000},
            {"text": text, **kwargs})

    def ocr_assert(self, text: str, **kwargs) -> dict:
        """断言文字存在。

        Args:
            text: 要断言的文字。
            timeout: 超时时间（秒），默认 5。
        """
        return self._exec("ocr_assert",
            {"value": text, "timeout": kwargs.get("timeout", 5) * 1000},
            {"text": text, **kwargs})

    def ocr_get_text(self, **kwargs) -> str:
        """获取屏幕所有文字。

        Returns:
            识别到的文字内容。
        """
        return self._exec_str("ocr_get_text",
            {"value": "", "timeout": kwargs.get("timeout", 5) * 1000},
            {**kwargs})

    def ocr_paste(self, text: str, content: str, **kwargs) -> dict:
        """OCR 定位后粘贴剪贴板内容。

        Args:
            text: 要定位的文字。
            content: 剪贴板内容。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        return self._exec("ocr_paste",
            {"value": text, "text": content, **self._ocr_params(kwargs)},
            {"text": text, "content": content, **kwargs})

    def ocr_move(self, text: str, **kwargs) -> dict:
        """OCR 定位后移动鼠标（仅桌面端支持）。

        Args:
            text: 要定位的文字。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        return self._exec("ocr_move",
            {"value": text, **self._ocr_params(kwargs)},
            {"text": text, **kwargs})

    def ocr_double_click(self, text: str, **kwargs) -> dict:
        """OCR 定位后双击。

        Args:
            text: 要识别并双击的文字。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        return self._exec("ocr_double_click",
            {"value": text, **self._ocr_params(kwargs)},
            {"text": text, **kwargs})

    def ocr_exist(self, text: str, **kwargs) -> bool:
        """检查文字是否存在。

        Args:
            text: 要检查的文字。支持 `reg_` 前缀正则匹配，如 `reg_\\d+`。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。

        Returns:
            True 如果文字存在，False 如果不存在。不抛异常。
        """
        return self._exec_bool("ocr_exist",
            {"value": text, **self._ocr_params(kwargs)},
            {"text": text, **kwargs})

    def ocr_get_position(self, text: str, **kwargs) -> list:
        """获取文字坐标列表。

        Args:
            text: 要查找的文字内容。支持 `reg_` 前缀正则匹配，如 `reg_\\d+`。
            timeout: 超时时间（秒），默认 5。

        Returns:
            坐标列表 [[x1, y1], [x2, y2], ...]，坐标顺序：精确匹配 → 模糊匹配。
        """
        return self._exec_list("ocr_get_position",
            {"value": text, "timeout": kwargs.get("timeout", 5) * 1000},
            {"text": text, **kwargs})

    def ocr_click_same_row_text(
        self, anchor_text: str, target_text: str, **kwargs
    ) -> dict:
        """点击锚点文本同一行的目标文本。

        Args:
            anchor_text: 锚点文本内容。
            target_text: 目标文本内容。
            anchor_index: 锚点文本索引（从 0 开始），默认 0。
            target_index: 目标文本索引（从 0 开始），默认 0。
            row_tolerance: 水平带范围（像素），默认 20。
            timeout: 超时时间（秒），默认 5。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        action_data = {
            "anchor_text": anchor_text,
            "value": target_text,
            **self._same_row_params(kwargs),
            "timeout": kwargs.get("timeout", 5) * 1000,
        }
        if "offset" in kwargs:
            action_data["offset"] = kwargs["offset"]

        return self._exec("ocr_click_same_row_text", action_data,
            {"anchor_text": anchor_text, "target_text": target_text, **kwargs})

    def ocr_click_same_row_image(
        self, anchor_text: str, image_path: str, **kwargs
    ) -> dict:
        """点击锚点文本同一行的目标图片。

        Args:
            anchor_text: 锚点文本内容。
            image_path: 目标图片路径。
            anchor_index: 锚点文本索引（从 0 开始），默认 0。
            target_index: 目标图片索引（从 0 开始），默认 0。
            row_tolerance: 水平带范围（像素），默认 20。
            confidence: 匹置信度（0-1），默认 0.8。
            timeout: 超时时间（秒），默认 5。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        action_data = {
            "anchor_text": anchor_text,
            "image_base64": image_base64,
            **self._same_row_params(kwargs),
            "threshold": kwargs.get("confidence", 0.8),
            "timeout": kwargs.get("timeout", 5) * 1000,
        }
        if "offset" in kwargs:
            action_data["offset"] = kwargs["offset"]

        return self._exec("ocr_click_same_row_image", action_data,
            {"anchor_text": anchor_text, "image_path": image_path, **kwargs})

    def ocr_check_same_row_text(
        self, anchor_text: str, target_text: str, **kwargs
    ) -> dict:
        """检查锚点文本同一行的目标文本是否存在。

        Args:
            anchor_text: 锚点文本内容。
            target_text: 目标文本内容。
            anchor_index: 锚点文本索引（从 0 开始），默认 0。
            target_index: 目标文本索引（从 0 开始），默认 0。
            row_tolerance: 水平带范围（像素），默认 20。
            timeout: 超时时间（秒），默认 5。
        """
        return self._exec("ocr_check_same_row_text",
            {
                "anchor_text": anchor_text,
                "value": target_text,
                **self._same_row_params(kwargs),
                "timeout": kwargs.get("timeout", 5) * 1000,
            },
            {"anchor_text": anchor_text, "target_text": target_text, **kwargs})

    def ocr_check_same_row_image(
        self, anchor_text: str, image_path: str, **kwargs
    ) -> dict:
        """检查锚点文本同一行的目标图片是否存在。

        Args:
            anchor_text: 锚点文本内容。
            image_path: 目标图片路径。
            anchor_index: 锚点文本索引（从 0 开始），默认 0。
            target_index: 目标图片索引（从 0 开始），默认 0。
            row_tolerance: 水平带范围（像素），默认 20。
            confidence: 匹置信度（0-1），默认 0.8。
            timeout: 超时时间（秒），默认 5。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        return self._exec("ocr_check_same_row_image",
            {
                "anchor_text": anchor_text,
                "image_base64": image_base64,
                **self._same_row_params(kwargs),
                "threshold": kwargs.get("confidence", 0.8),
                "timeout": kwargs.get("timeout", 5) * 1000,
            },
            {"anchor_text": anchor_text, "image_path": image_path, **kwargs})

    # ── 图像识别动作 ─────────────────────────────────────────

    def _load_image_as_base64(self, image_path: str) -> Optional[str]:
        """将本地图片转换为 base64 编码。

        Args:
            image_path: 图片路径（相对或绝对）。

        Returns:
            base64 编码的图片内容，如果文件不存在则返回 None。
        """
        return load_image_as_base64(image_path)

    def _execute_exist_check(
        self,
        method: str,
        action_data: Dict[str, Any],
        log_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行 exist 类型操作，不抛异常，返回 exists 结果。

        ocr_exist 和 image_exist 无论是否存在都返回 SUCCESS 状态，
        不会抛出 AWError。

        Args:
            method: 方法名。
            action_data: 原始 action 数据。
            log_args: 用于日志记录的参数。

        Returns:
            包含 exists 字段的结果字典。
        """
        import json

        # 公共 AW 继承 User 的平台
        platform = self.PLATFORM
        if platform == "common" and self.user:
            platform = self.user.platform

        # 检查是否处于收集模式
        if is_collecting():
            queue = get_action_queue()
            if queue is not None:
                user_id = self.user.user_id if self.user else ""
                parent_aw = self._find_parent_aw()
                action_obj = Action(
                    action_data=action_data,
                    platform=platform,
                    user_id=user_id,
                    aw_name=self._aw_name,
                    method=method,
                    log_args=log_args,
                    client=self.client,
                    parent_aw=parent_aw,
                )
                queue.append(action_obj)
                return {"exists": False}  # 收集模式返回默认值

        # 同步执行模式
        parent_aw = self._find_parent_aw()
        logger = ReportLogger.get_current()
        start_time = time.time()

        try:
            result = self.client.execute(platform, [action_data])
        except Exception as e:
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
            # exist 方法不抛异常，返回 False
            return {"exists": False}

        duration_ms = int((time.time() - start_time) * 1000)

        action_result = result.get("actions", [{}])[0] if result.get("actions") else {}
        success = action_result.get("status") == "success"

        # 解析 output 中的 exists 结果
        output = action_result.get("output", "")
        exists = False
        if output:
            try:
                output_data = json.loads(output)
                exists = output_data.get("exists", False)
            except (json.JSONDecodeError, TypeError):
                exists = False

        # 构建完整结果
        full_result = {
            "status": action_result.get("status", "success"),
            "platform": platform,
            "duration_ms": action_result.get("duration_ms", 0),
            "actions": [action_result],
            "output": output,
            "exists": exists,
        }

        user_id = self.user.user_id if self.user else ""
        user_account = self.user.account if self.user else ""
        user_name = self.user.name if self.user else ""

        logger.log_aw_call(
            aw_name=self._aw_name,
            method=method,
            args={"user_id": user_id, "user_account": user_account, "user_name": user_name, **log_args},
            success=success,
            result=full_result,
            duration_ms=duration_ms,
            parent_aw=parent_aw,
        )

        logger.log_worker_call(
            api="task/execute",
            params={"platform": platform, "method": method, "user_id": user_id, "user_account": user_account, "user_name": user_name, **log_args},
            success=success,
            response=full_result,
            duration_ms=duration_ms,
        )

        # exist 方法不抛异常，直接返回结果
        return {"exists": exists}

    # ── 参数构建器 ─────────────────────────────────────────

    def _ocr_params(self, kwargs: dict) -> dict:
        """构建 OCR 类 action 的通用参数。

        包含：timeout(默认5秒转毫秒)、index(默认0)、offset
        """
        params = {
            "timeout": kwargs.get("timeout", 5) * 1000,
            "index": kwargs.get("index", 0),  # 总是设置，默认值 0
        }
        if "offset" in kwargs:
            params["offset"] = kwargs["offset"]
        return params

    def _image_params(self, kwargs: dict) -> dict:
        """构建 Image 类 action 的通用参数。

        包含：timeout、threshold(默认0.8)、index、offset
        """
        params = {
            "timeout": kwargs.get("timeout", 5) * 1000,
            "threshold": kwargs.get("confidence", 0.8),  # alias
        }
        if "index" in kwargs:
            params["index"] = kwargs["index"]
        if "offset" in kwargs:
            params["offset"] = kwargs["offset"]
        return params

    def _same_row_params(self, kwargs: dict) -> dict:
        """构建 same_row 类 action 的通用参数。

        包含：anchor_index、target_index、row_tolerance
        """
        return {
            "anchor_index": kwargs.get("anchor_index", 0),
            "target_index": kwargs.get("target_index", 0),
            "row_tolerance": kwargs.get("row_tolerance", 20),
        }

    # ── 执行包装层 ─────────────────────────────────────────

    def _exec(
        self,
        action_type: str,
        action_data: dict,
        log_args: dict,
    ) -> dict:
        """执行 action 并记录日志，失败时抛 AWError。

        Args:
            action_type: 动作类型，如 "ocr_click"
            action_data: 发给 worker 的完整 action dict
            log_args: 用于日志记录的参数
        """
        full_action_data = {"action_type": action_type, **action_data}
        return self._execute_with_log(action_type, full_action_data, log_args)

    def _exec_bool(self, action_type: str, action_data: dict, log_args: dict) -> bool:
        """执行 exist 类 action，返回 bool，不抛异常。"""
        full_action_data = {"action_type": action_type, **action_data}
        result = self._execute_exist_check(action_type, full_action_data, log_args)
        return result.get("exists", False)

    def _exec_str(
        self,
        action_type: str,
        action_data: dict,
        log_args: dict,
        field: str = "output"
    ) -> str:
        """执行 action 并提取 str 返回值。"""
        result = self._exec(action_type, action_data, log_args)
        if result.get("actions"):
            return result["actions"][0].get(field, "")
        return ""

    def _exec_list(
        self,
        action_type: str,
        action_data: dict,
        log_args: dict,
        key: str = "positions"
    ) -> list:
        """执行 action 并解析 list 返回值（如 positions）。"""
        import json
        result = self._exec(action_type, action_data, log_args)
        if result.get("actions"):
            output = result["actions"][0].get("output", "")
            if output:
                try:
                    return json.loads(output).get(key, [])
                except json.JSONDecodeError:
                    pass
        return []

    def image_click(self, image_path: str, **kwargs) -> dict:
        """图像识别点击。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("image_click",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs})

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
        return self._exec("image_wait",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs})

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
        return self._exec("image_assert",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs})

    def image_click_near_text(self, image_path: str, text: str, **kwargs) -> dict:
        """点击文本附近最近的图像。

        Args:
            image_path: 图片路径。
            text: 文本内容。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            max_distance: 最大搜索距离（像素），默认 500。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("image_click_near_text",
            {"image_base64": image_base64, "value": text, "end_x": kwargs.get("max_distance", 500), **self._image_params(kwargs)},
            {"image_path": image_path, "text": text, **kwargs})

    def image_move(self, image_path: str, **kwargs) -> dict:
        """图像识别后移动鼠标（仅桌面端支持）。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 移动偏移量 {"x": 0, "y": 0}。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("image_move",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs})

    def image_double_click(self, image_path: str, **kwargs) -> dict:
        """图像识别后双击。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("image_double_click",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs})

    def image_exist(self, image_path: str, **kwargs) -> bool:
        """检查图像是否存在。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            index: 选择第几个匹配结果（从 0 开始）。

        Returns:
            True 如果图像存在，False 如果不存在。不抛异常。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec_bool("image_exist",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs})

    def image_get_position(self, image_path: str, **kwargs) -> list:
        """获取图像坐标列表。

        Args:
            image_path: 图片路径。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。

        Returns:
            坐标列表 [[x1, y1], [x2, y2], ...]。
        """
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec_list("image_get_position",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs})

    def click(self, x: int, y: int) -> dict:
        """坐标点击。

        Args:
            x: X 坐标。
            y: Y 坐标。
        """
        return self._exec("click", {"x": x, "y": y}, {"x": x, "y": y})

    def double_click(self, x: int, y: int, **kwargs) -> dict:
        """坐标双击。

        Args:
            x: X 坐标。
            y: Y 坐标。
            offset: 点击偏移量 {"x": 0, "y": 0}。
        """
        action_data = {"x": x, "y": y}
        if "offset" in kwargs:
            action_data["offset"] = kwargs["offset"]
        return self._exec("double_click", action_data, {"x": x, "y": y, **kwargs})

    def move(self, x: int, y: int, **kwargs) -> dict:
        """移动鼠标到指定坐标（仅桌面端支持）。

        Args:
            x: X 坐标。
            y: Y 坐标。
            offset: 移动偏移量 {"x": 0, "y": 0}。
        """
        action_data = {"x": x, "y": y}
        if "offset" in kwargs:
            action_data["offset"] = kwargs["offset"]
        return self._exec("move", action_data, {"x": x, "y": y, **kwargs})

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, **kwargs) -> dict:
        """滑动操作。

        Args:
            from_x: 起点 X 坐标。
            from_y: 起点 Y 坐标。
            to_x: 终点 X 坐标。
            to_y: 终点 Y 坐标。
            duration: 滑动持续时间（毫秒）。
        """
        action_data = {"from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}}
        if "duration" in kwargs:
            action_data["duration"] = kwargs["duration"]
        return self._exec("swipe", action_data,
            {"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y, **kwargs})

    def input_text(self, x: int, y: int, text: str) -> dict:
        """在指定坐标输入文本。

        Args:
            x: X 坐标。
            y: Y 坐标。
            text: 要输入的文本。
        """
        return self._exec("input", {"x": x, "y": y, "text": text}, {"x": x, "y": y, "text": text})

    # ── 其他动作 ─────────────────────────────────────────

    def press(self, key: str) -> dict:
        """按键操作。"""
        return self._exec("press", {"key": key}, {"key": key})

    def wait(self, duration: float) -> dict:
        """固定等待。"""
        duration_ms = int(duration * 1000)
        return self._exec("wait", {"value": str(duration_ms)}, {"duration_ms": duration_ms})

    def start_app(self, app_id: str) -> dict:
        """启动应用。"""
        return self._exec("start_app", {"value": app_id}, {"app_id": app_id})

    def stop_app(self, app_id: str) -> dict:
        """关闭应用。"""
        return self._exec("stop_app", {"value": app_id}, {"app_id": app_id})

    def navigate(self, url: str) -> dict:
        """导航到 URL（Web 端专用）。"""
        return self._exec("navigate", {"value": url}, {"url": url})

    def switched_page(self, page_index: int) -> dict:
        """切换到指定页面（Web 端专用）。"""
        return self._exec("switched_page", {"value": str(page_index)}, {"page_index": page_index})

    def close_page(self) -> dict:
        """关闭当前页面（Web 端专用）。"""
        return self._exec("close_page", {}, {})

    def web_image_upload(self, x: int, y: int, image_path: str) -> dict:
        """处理文件上传弹窗（Web 端专用）。"""
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("web_image_upload",
            {"x": x, "y": y, "image_base64": image_base64},
            {"x": x, "y": y, "image_path": image_path})

    def cmd_exec(self, command: str, **kwargs) -> dict:
        """在宿主机执行命令。"""
        timeout_ms = kwargs.get("timeout", 30) * 1000
        return self._exec("cmd_exec",
            {"value": command, "timeout": timeout_ms},
            {"command": command, **kwargs})

    def screenshot(self) -> str:
        """截图并返回 base64。

        Returns:
            截图的 base64 编码，失败返回空字符串。
        """
        # 公共 AW 继承 User 的平台
        platform = self.PLATFORM
        if platform == "common" and self.user:
            platform = self.user.platform

        user_id = self.user.user_id if self.user else None
        action_data = {
            "action_type": "screenshot",
            "value": f"screenshot_{int(time.time() * 1000)}",
        }
        # 直接调用 execute 以传递 user_id
        result = self.client.execute(platform, [action_data], user_id=user_id)
        if result.get("status") == "success" and result.get("actions"):
            action = result["actions"][0]
            # 优先取 screenshot 字段，其次取 output 字段
            return action.get("screenshot") or action.get("output", "")
        return ""