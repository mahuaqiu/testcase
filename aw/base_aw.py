"""AW 基类。"""

import functools
import inspect
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from common.testagent_client import TestagentClient
from common.report_logger import ReportLogger
from common.parallel import is_collecting, get_action_queue, Action
from common.utils import load_image_as_base64

if TYPE_CHECKING:
    from common.user import User

logger = logging.getLogger(__name__)


class AWError(Exception):
    """AW 操作失败异常。"""

    def __init__(self, method: str, result: Dict[str, Any]):
        self.method = method
        self.result = result
        error_msg = result.get("error", "未知错误")
        super().__init__(f"{method} 执行失败: {error_msg}")


class ParallelModeError(Exception):
    """并行模式下非法使用原子操作返回值的异常。"""

    def __init__(self, method: str, usage: str):
        msg = (
            f"不能在并行模式下使用 {method} 返回值做 {usage}。\n"
            f"原因：收集模式下原子操作未执行，返回值无效。\n"
            f"解决：\n"
            f"  1) 将该操作移到 parallel() 上下文外执行\n"
            f"  2) 使用不依赖返回值的原子操作（如 ocr_assert 替代 ocr_exist）\n"
            f"  3) 如必须依赖返回值，请在该用户单独的 parallel() 中处理"
        )
        super().__init__(msg)


class PendingResult:
    """并行收集模式下的待定返回值。

    当原子操作在 parallel() 上下文中被调用时，返回此对象。
    实际使用（条件判断、迭代等）时会抛异常，提醒用户不能在并行模式下依赖原子操作返回值。
    """

    def __init__(self, method: str, return_type: str = "bool"):
        self._method = method
        self._return_type = return_type

    def __bool__(self):
        raise ParallelModeError(self._method, "条件判断")

    def __str__(self):
        raise ParallelModeError(self._method, "字符串操作")

    def __repr__(self):
        return f"<PendingResult[{self._return_type}]: {self._method}>"

    def __len__(self):
        raise ParallelModeError(self._method, "列表操作")

    def __iter__(self):
        raise ParallelModeError(self._method, "迭代操作")

    def __getitem__(self, key):
        raise ParallelModeError(self._method, "索引访问")

    def get(self, key, default=None):
        """dict-like get 方法，触发异常提示。"""
        raise ParallelModeError(self._method, "数据访问")


def _auto_log_aw_call(func):
    """自动记录业务方法参数的装饰器。

    用于 do_*/should_* 方法，在执行后记录方法参数和结果。
    失败时自动截图并记录错误信息。
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

        # 用户信息
        user_id = self.user.user_id if self.user else ""
        user_account = self.user.account if self.user else ""
        user_name = self.user.name if self.user else ""
        user_ip = self.user.ip if self.user else ""

        # 收集模式下，收集模式也需要捕获异常
        # 注意：原子操作在收集模式下不抛异常，但业务方法可能直接抛异常
        if is_collecting():
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                # 失败：从异常中提取 error_screenshot（如果已有）
                error_screenshot = ""
                has_atomic_screenshot = False  # 标记截图是否来自原子操作

                if isinstance(e, AWError) and "error_screenshot" in e.result:
                    error_screenshot = e.result.get("error_screenshot", "")
                    has_atomic_screenshot = True  # 截图来自原子操作，业务方法日志不记录
                if not error_screenshot:
                    try:
                        error_screenshot = self.screenshot()
                    except Exception:
                        pass

                error_result = {
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
                # 只有截图来自业务方法自身时才记录到业务方法日志
                if error_screenshot and not has_atomic_screenshot:
                    error_result["error_screenshot"] = error_screenshot

                logger = ReportLogger.get_current()
                logger.log_aw_call(
                    aw_name=self._aw_name,
                    method=func.__name__,
                    args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "user_ip": user_ip, **method_args},
                    success=False,
                    result=error_result,
                    duration_ms=0,
                    parent_aw=parent_aw,
                    is_business_method=True,
                    request_id="",  # 业务方法没有直接的 request_id
                )
                raise

        # 同步模式：记录日志
        logger = ReportLogger.get_current()
        start_time = time.time()

        try:
            # 执行原方法
            result = func(self, *args, **kwargs)

            # 成功：记录日志
            duration_ms = int((time.time() - start_time) * 1000)

            logger.log_aw_call(
                aw_name=self._aw_name,
                method=func.__name__,
                args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "user_ip": user_ip, **method_args},
                success=True,
                result={},
                duration_ms=duration_ms,
                parent_aw=parent_aw,
                is_business_method=True,
                request_id="",  # 业务方法没有直接的 request_id
            )

            return result

        except Exception as e:
            # 失败：截图并记录日志
            duration_ms = int((time.time() - start_time) * 1000)

            # 失败时截图：优先从异常中提取已有的 error_screenshot（如果是 AWError）
            error_screenshot = ""
            has_atomic_screenshot = False  # 标记截图是否来自原子操作

            if isinstance(e, AWError) and "error_screenshot" in e.result:
                error_screenshot = e.result.get("error_screenshot", "")
                has_atomic_screenshot = True  # 截图来自原子操作，业务方法日志不记录
            if not error_screenshot:
                try:
                    # Web 平台需要 system 级别截图
                    screenshot_kwargs = {}
                    if self.PLATFORM == "web" or (self.PLATFORM == "common" and self.user and self.user.platform == "web"):
                        screenshot_kwargs["level"] = "system"
                    error_screenshot = self.screenshot(**screenshot_kwargs)
                except Exception:
                    pass  # 截图失败不影响主流程

            # 记录失败日志
            error_result = {
                "error": str(e),
                "error_type": type(e).__name__,
            }
            # 只有截图来自业务方法自身时才记录到业务方法日志
            if error_screenshot and not has_atomic_screenshot:
                error_result["error_screenshot"] = error_screenshot

            logger.log_aw_call(
                aw_name=self._aw_name,
                method=func.__name__,
                args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "user_ip": user_ip, **method_args},
                success=False,
                result=error_result,
                duration_ms=duration_ms,
                parent_aw=parent_aw,
                is_business_method=True,
                request_id="",  # 业务方法没有直接的 request_id
            )

            # 重新抛出异常
            raise

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
        window: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行操作并记录日志，失败时抛出异常。

        在 parallel() 上下文中收集 action_data，否则立即执行。

        Args:
            method: 方法名。
            action_data: 原始 action 数据（发给服务端）。
            log_args: 用于日志记录的参数。
            window: 窗口定位参数（仅 Windows 平台）。

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
                user_name = self.user.name if self.user else ""
                user_account = self.user.account if self.user else ""
                user_ip = self.user.ip if self.user else ""
                # 获取 parent_aw（用于日志聚合）
                parent_aw = self._find_parent_aw()
                action_obj = Action(
                    action_data=action_data,
                    platform=platform,
                    user_id=user_id,
                    user_name=user_name,
                    user_account=user_account,
                    user_ip=user_ip,
                    aw_name=self._aw_name,
                    method=method,
                    log_args=log_args,
                    client=self.client,
                    parent_aw=parent_aw,  # 传递 parent_aw 以支持日志聚合
                    window=window,
                )
                queue.append(action_obj)
                return None  # 收集模式标记

        # 同步执行模式
        # 自动识别 parent_aw
        parent_aw = self._find_parent_aw()
        logger = ReportLogger.get_current()
        start_time = time.time()

        try:
            # 调用 client.execute（批量接口，传入单个 action）
            # iOS/Android 平台需要 device_id
            device_id = None
            if platform in ("ios", "android") and self.user:
                device_id = self.user.device_id
            result = self.client.execute(platform, [action_data], device_id=device_id, window=window)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            # 检测是否是连接关闭错误（上层可能重试）
            # 连接类错误不记录失败日志，避免重试成功后出现重复失败日志
            error_msg = str(e)
            is_connection_closed = any(keyword in error_msg for keyword in [
                "Connection aborted",
                "RemoteDisconnected",
                "Remote end closed connection",
            ])

            if not is_connection_closed:
                # 非连接类错误：记录失败日志
                logger.log_aw_call(
                    aw_name=self._aw_name,
                    method=method,
                    args=log_args,
                    success=False,
                    result={"error": str(e)},
                    duration_ms=duration_ms,
                    parent_aw=parent_aw,
                    request_id="",  # 异常时无 request_id
                )
            raise

        duration_ms = int((time.time() - start_time) * 1000)

        # 从 actions 列表中优先提取失败的结果（包含错误信息和 OCR 数据）
        actions = result.get("actions", [])
        failed_actions = [a for a in actions if a.get("status") == "failed"]
        action_result = failed_actions[0] if failed_actions else (actions[0] if actions else {})
        success = action_result.get("status") == "success"
        # 提取 request_id（用于问题定位）
        request_id = action_result.get("request_id", "")

        # 失败时获取截图，优先使用 Worker 返回的 error_screenshot
        target_image_base64 = ""
        target_image_path = ""
        if not success:
            # 优先使用 Worker 返回的 error_screenshot（失败瞬间的截图）
            error_screenshot = result.get("error_screenshot", "")
            if not error_screenshot:
                # Worker 没返回，手动截图
                # Web 平台需要 system 级别截图（截取原生对话框）
                screenshot_kwargs = {}
                if platform == "web":
                    screenshot_kwargs["level"] = "system"
                error_screenshot = self.screenshot(**screenshot_kwargs)
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
        user_ip = self.user.ip if self.user else ""

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
        if "ocr_info" in action_result:
            full_result["ocr_info"] = action_result["ocr_info"]

        logger.log_aw_call(
            aw_name=self._aw_name,
            method=method,
            args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "user_ip": user_ip, **log_args},
            success=success,
            result=full_result,
            duration_ms=duration_ms,
            target_image=target_image_base64,
            target_image_path=target_image_path,
            parent_aw=parent_aw,
            request_id=request_id,
        )

        # 记录 worker 调用日志（用于调试，报告中不显示）
        logger.log_worker_call(
            api="task/execute",
            params={"platform": platform, "method": method, "user_id": user_id, "user_account": user_account, "user_name": user_name, "user_ip": user_ip, **log_args},
            success=success,
            response=full_result,
            duration_ms=duration_ms,
        )

        # 失败时抛出异常
        if not success:
            raise AWError(f"{self._aw_name}.{method}", full_result)

        return full_result

    # ── OCR 动作 ─────────────────────────────────────────

    def ocr_click(self, text: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """OCR 识别并点击。

        Args:
            text: 要识别并点击的文字。
            window_class: 窗口类名（仅 Windows 平台，精确匹配），如 "HwmMainWndClass"。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        params = self._ocr_params(kwargs)
        if "click_duration" in kwargs:
            params["click_duration"] = kwargs["click_duration"]
        return self._exec("ocr_click",
            {"value": text, **params},
            {"text": text, **kwargs},
            window=window)

    def ocr_input(self, label: str, content: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """OCR 定位后输入。

        Args:
            label: 要定位的文字标签。
            content: 要输入的内容。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 输入偏移量 {"x": 0, "y": 0}。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        params = self._ocr_params(kwargs)
        if "click_duration" in kwargs:
            params["click_duration"] = kwargs["click_duration"]
        return self._exec("ocr_input",
            {"value": label, "text": content, **params},
            {"label": label, "content": content, **kwargs},
            window=window)

    def ocr_wait(self, text: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """等待文字出现。

        Args:
            text: 要等待的文字。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        action_data = {"value": text, "timeout": kwargs.get("timeout", 5) * 1000}
        if "level" in kwargs:
            action_data["level"] = kwargs["level"]
            if "monitor" in kwargs:
                action_data["monitor"] = kwargs["monitor"]
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            action_data["region"] = resolved
        return self._exec("ocr_wait", action_data, {"text": text, **kwargs}, window=window)

    def ocr_assert(self, text, negate: bool = False, window_class: Optional[str] = None, **kwargs) -> dict:
        """断言文字存在或不存在（单次截图断言）。

        Args:
            text: 要断言的文字。支持 list 传参批量验证：["文字1", "文字2", "文字3"]。
            negate: 断言不存在，True 时断言文字不存在。
                - list 场景：negate=true 要求所有文字都不存在才算通过（严格否定）
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        action_data = {"value": text, "negate": negate}
        if "level" in kwargs:
            action_data["level"] = kwargs["level"]
            if "monitor" in kwargs:
                action_data["monitor"] = kwargs["monitor"]
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            action_data["region"] = resolved
        return self._exec("ocr_assert", action_data, {"text": text, "negate": negate, **kwargs}, window=window)

    def ocr_get_text(self, window_class: Optional[str] = None, **kwargs) -> str:
        """获取屏幕所有文字。

        Args:
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。

        Returns:
            识别到的文字内容。
        """
        window = self._build_window(window_class)
        action_data = {"value": ""}
        if "level" in kwargs:
            action_data["level"] = kwargs["level"]
            if "monitor" in kwargs:
                action_data["monitor"] = kwargs["monitor"]
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            action_data["region"] = resolved
        return self._exec_str("ocr_get_text", action_data, {**kwargs}, window=window)

    def ocr_move(self, text: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """OCR 定位后移动鼠标（仅桌面端支持）。

        Args:
            text: 要定位的文字。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        return self._exec("ocr_move",
            {"value": text, **self._ocr_params(kwargs)},
            {"text": text, **kwargs},
            window=window)

    def ocr_double_click(self, text: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """OCR 定位后双击。

        Args:
            text: 要识别并双击的文字。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        return self._exec("ocr_double_click",
            {"value": text, **self._ocr_params(kwargs)},
            {"text": text, **kwargs},
            window=window)

    def ocr_exist(self, text, window_class: Optional[str] = None, **kwargs) -> bool:
        """检查文字是否存在。

        Args:
            text: 要检查的文字。支持 list 传参批量检查：["文字1", "文字2", "文字3"]。
                也支持 `reg_` 前缀正则匹配，如 `reg_\\d+`。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            index: 选择第几个匹配结果（从 0 开始）。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。

        Returns:
            True 如果文字存在，False 如果不存在。不抛异常。
        """
        window = self._build_window(window_class)
        return self._exec_bool("ocr_exist",
            {"value": text, **self._ocr_params(kwargs)},
            {"text": text, **kwargs},
            window=window)

    def ocr_get_position(self, text: str, window_class: Optional[str] = None, **kwargs) -> list:
        """获取文字坐标列表。

        Args:
            text: 要查找的文字内容。支持 `reg_` 前缀正则匹配，如 `reg_\\d+`。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。

        Returns:
            坐标列表 [[x1, y1], [x2, y2], ...]，坐标顺序：精确匹配 → 模糊匹配。
        """
        window = self._build_window(window_class)
        action_data = {"value": text}
        if "level" in kwargs:
            action_data["level"] = kwargs["level"]
            if "monitor" in kwargs:
                action_data["monitor"] = kwargs["monitor"]
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            action_data["region"] = resolved
        return self._exec_list("ocr_get_position", action_data, {"text": text, **kwargs}, window=window)

    def ocr_click_same_row_text(
        self, anchor_text: str, target_text: str, window_class: Optional[str] = None, **kwargs
    ) -> dict:
        """点击锚点文本同一行的目标文本。

        Args:
            anchor_text: 锚点文本内容。
            target_text: 目标文本内容。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            anchor_index: 锚点文本索引（从 0 开始），默认 0。
            target_index: 目标文本索引（从 0 开始），默认 0。
            row_tolerance: 水平带范围（像素），默认 20。
            timeout: 超时时间（秒），默认 5。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
        """
        window = self._build_window(window_class)
        action_data = {
            "anchor_text": anchor_text,
            "value": target_text,
            **self._same_row_params(kwargs),
            "timeout": kwargs.get("timeout", 5) * 1000,
        }
        if "offset" in kwargs:
            action_data["offset"] = kwargs["offset"]
        if "click_duration" in kwargs:
            action_data["click_duration"] = kwargs["click_duration"]
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            action_data["region"] = resolved

        return self._exec("ocr_click_same_row_text", action_data,
            {"anchor_text": anchor_text, "target_text": target_text, **kwargs}, window=window)

    def ocr_click_same_row_image(
        self, anchor_text: str, image_path: str, window_class: Optional[str] = None, **kwargs
    ) -> dict:
        """点击锚点文本同一行的目标图片。

        Args:
            anchor_text: 锚点文本内容。
            image_path: 目标图片路径。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            anchor_index: 锚点文本索引（从 0 开始），默认 0。
            target_index: 目标图片索引（从 0 开始），默认 0。
            row_tolerance: 水平带范围（像素），默认 20。
            confidence: 匹置信度（0-1），默认 0.8。
            timeout: 超时时间（秒），默认 5。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
        """
        window = self._build_window(window_class)
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
        if "click_duration" in kwargs:
            action_data["click_duration"] = kwargs["click_duration"]
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            action_data["region"] = resolved

        return self._exec("ocr_click_same_row_image", action_data,
            {"anchor_text": anchor_text, "image_path": image_path, **kwargs}, window=window)

    def ocr_check_same_row_text(
        self, anchor_text: str, target_text: str, window_class: Optional[str] = None, **kwargs
    ) -> bool:
        """检查锚点文本同一行的目标文本是否存在。

        Args:
            anchor_text: 锚点文本内容。
            target_text: 目标文本内容。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            anchor_index: 锚点文本索引（从 0 开始），默认 0。
            target_index: 目标文本索引（从 0 开始），默认 0。
            row_tolerance: 水平带范围（像素），默认 20。
            timeout: 超时时间（秒），默认 5。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。

        Returns:
            True 如果存在，False 如果不存在。不抛异常。
        """
        window = self._build_window(window_class)
        action_data = {
            "anchor_text": anchor_text,
            "value": target_text,
            **self._same_row_params(kwargs),
            "timeout": kwargs.get("timeout", 5) * 1000,
        }
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            action_data["region"] = resolved
        return self._exec_bool("ocr_check_same_row_text", action_data,
            {"anchor_text": anchor_text, "target_text": target_text, **kwargs}, window=window)

    def ocr_check_same_row_image(
        self, anchor_text: str, image_path: str, window_class: Optional[str] = None, **kwargs
    ) -> bool:
        """检查锚点文本同一行的目标图片是否存在。

        Args:
            anchor_text: 锚点文本内容。
            image_path: 目标图片路径。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            anchor_index: 锚点文本索引（从 0 开始），默认 0。
            target_index: 目标图片索引（从 0 开始），默认 0。
            row_tolerance: 水平带范围（像素），默认 20。
            confidence: 匹置信度（0-1），默认 0.8。
            timeout: 超时时间（秒），默认 5。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。

        Returns:
            True 如果存在，False 如果不存在。不抛异常。
        """
        window = self._build_window(window_class)
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
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            action_data["region"] = resolved

        return self._exec_bool("ocr_check_same_row_image", action_data,
            {"anchor_text": anchor_text, "image_path": image_path, **kwargs}, window=window)

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
        window: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行 exist 类型操作，不抛异常，返回 exists 结果。

        ocr_exist 和 image_exist 无论是否存在都返回 SUCCESS 状态，
        不会抛出 AWError。

        Args:
            method: 方法名。
            action_data: 原始 action 数据。
            log_args: 用于日志记录的参数。
            window: 窗口定位参数（仅 Windows 平台）。

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
                user_name = self.user.name if self.user else ""
                user_account = self.user.account if self.user else ""
                user_ip = self.user.ip if self.user else ""
                parent_aw = self._find_parent_aw()
                action_obj = Action(
                    action_data=action_data,
                    platform=platform,
                    user_id=user_id,
                    user_name=user_name,
                    user_account=user_account,
                    user_ip=user_ip,
                    aw_name=self._aw_name,
                    method=method,
                    log_args=log_args,
                    client=self.client,
                    parent_aw=parent_aw,
                    window=window,
                )
                queue.append(action_obj)
                return None  # 收集模式标记

        # 同步执行模式
        parent_aw = self._find_parent_aw()
        logger = ReportLogger.get_current()
        start_time = time.time()

        # iOS/Android 需要传递 device_id
        device_id = None
        if platform in ("ios", "android") and self.user:
            device_id = self.user.device_id

        try:
            result = self.client.execute(platform, [action_data], device_id=device_id, window=window)
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
                request_id="",  # 异常时无 request_id
            )
            # exist 方法不抛异常，返回 False
            return {"exists": False}

        duration_ms = int((time.time() - start_time) * 1000)

        action_result = result.get("actions", [{}])[0] if result.get("actions") else {}
        success = action_result.get("status") == "success"
        # 提取 request_id（用于问题定位）
        request_id = action_result.get("request_id", "")

        # 解析 output 中的 exists 结果
        # output 可能是 dict（已解析）或 str（JSON 字串）
        output = action_result.get("output", "")
        exists = False
        if output:
            try:
                if isinstance(output, dict):
                    exists = output.get("exists", False)
                else:
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
        user_ip = self.user.ip if self.user else ""

        logger.log_aw_call(
            aw_name=self._aw_name,
            method=method,
            args={"user_id": user_id, "user_account": user_account, "user_name": user_name, "user_ip": user_ip, **log_args},
            success=success,
            result=full_result,
            duration_ms=duration_ms,
            parent_aw=parent_aw,
            request_id=request_id,
        )

        logger.log_worker_call(
            api="task/execute",
            params={"platform": platform, "method": method, "user_id": user_id, "user_account": user_account, "user_name": user_name, "user_ip": user_ip, **log_args},
            success=success,
            response=full_result,
            duration_ms=duration_ms,
        )

        # exist 方法不抛异常，直接返回结果
        return {"exists": exists}

    # ── 参数构建器 ─────────────────────────────────────────

    def _build_window(self, window_class: Optional[str]) -> Optional[Dict[str, Any]]:
        """构建 window 参数（仅 Windows 平台）。

        Args:
            window_class: 窗口类名（精确匹配）。

        Returns:
            {"class": window_class} 或 None。
        """
        if not window_class:
            return None

        # 公共 AW 继承 User 的平台
        platform = self.PLATFORM
        if platform == "common" and self.user:
            platform = self.user.platform

        # 仅 Windows 平台生效
        if platform != "windows":
            logger.warning(f"window_class only works on Windows, current: {platform}")
            return None

        return {"class": window_class}

    def _resolve_region(self, region) -> Optional[List[int]]:
        """解析区域参数，支持字符串名称或坐标数组。

        Args:
            region: 区域参数，可以是：
                - None: 不限制区域（全屏）
                - List[int]: 直接坐标 [x1, y1, x2, y2]
                - str: 区域名称，自动查找配置

        Returns:
            区域坐标 [x1, y1, x2, y2]，或 None
        """
        if region is None:
            return None
        if isinstance(region, list):
            return region  # 直接传坐标数组

        # 字符串名称 → 查配置
        from common.region_manager import RegionManager
        platform = self.user.platform if self.user else ""
        return RegionManager.get_instance().get_region(platform, region)

    def _ocr_params(self, kwargs: dict) -> dict:
        """构建 OCR 类 action 的通用参数。

        包含：timeout(默认5秒转毫秒)、index(默认0)、offset、region、level、monitor
        """
        params = {
            "timeout": kwargs.get("timeout", 5) * 1000,
            "index": kwargs.get("index", 0),  # 总是设置，默认值 0
        }
        if "offset" in kwargs:
            params["offset"] = kwargs["offset"]
        if "level" in kwargs:
            params["level"] = kwargs["level"]  # Web 平台专用，处理原生对话框
            # monitor 仅在 level: system 时有效，用于多显示器场景
            if "monitor" in kwargs:
                params["monitor"] = kwargs["monitor"]
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            params["region"] = resolved
        return params

    def _image_params(self, kwargs: dict) -> dict:
        """构建 Image 类 action 的通用参数。

        包含：timeout、threshold(默认0.8)、index、offset、region、level、monitor
        """
        params = {
            "timeout": kwargs.get("timeout", 5) * 1000,
            "threshold": kwargs.get("confidence", 0.8),  # alias
        }
        if "index" in kwargs:
            params["index"] = kwargs["index"]
        if "offset" in kwargs:
            params["offset"] = kwargs["offset"]
        if "level" in kwargs:
            params["level"] = kwargs["level"]  # Web 平台专用，处理原生对话框
            # monitor 仅在 level: system 时有效，用于多显示器场景
            if "monitor" in kwargs:
                params["monitor"] = kwargs["monitor"]
        resolved = self._resolve_region(kwargs.get("region"))
        if resolved:
            params["region"] = resolved
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
        window: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """执行 action 并记录日志，失败时抛 AWError。

        收集模式下返回 PendingResult，使用时会抛 ParallelModeError。
        """
        full_action_data = {"action_type": action_type, **action_data}
        result = self._execute_with_log(action_type, full_action_data, log_args, window=window)
        # 收集模式下返回 PendingResult（伪装成 dict）
        if result is None:
            return PendingResult(action_type, "dict")
        return result

    def _exec_bool(self, action_type: str, action_data: dict, log_args: dict, window: Optional[Dict[str, Any]] = None) -> bool:
        """执行 exist 类 action，返回 bool，不抛异常。

        收集模式下返回 PendingResult，使用时会抛 ParallelModeError。
        """
        full_action_data = {"action_type": action_type, **action_data}
        result = self._execute_exist_check(action_type, full_action_data, log_args, window=window)
        # 收集模式下返回 PendingResult
        if result is None:
            return PendingResult(action_type, "bool")
        return result.get("exists", False)

    def _exec_str(
        self,
        action_type: str,
        action_data: dict,
        log_args: dict,
        key: str = "text",
        window: Optional[Dict[str, Any]] = None,
    ) -> str:
        """执行 action 并提取 str 返回值（如 ocr_get_text 的 text 字段）。"""
        result = self._exec(action_type, action_data, log_args, window=window)
        if result.get("actions"):
            output = result["actions"][0].get("output", "")
            if output:
                # output 可能是 dict（已解析）或 str
                if isinstance(output, dict):
                    return output.get(key, "")
                return str(output)
        return ""

    def _exec_list(
        self,
        action_type: str,
        action_data: dict,
        log_args: dict,
        key: str = "positions",
        window: Optional[Dict[str, Any]] = None,
    ) -> list:
        """执行 action 并解析 list 返回值（如 positions）。"""
        import json
        result = self._exec(action_type, action_data, log_args, window=window)
        if result.get("actions"):
            output = result["actions"][0].get("output", "")
            if output:
                try:
                    # output 可能是 dict（已解析）或 str（JSON 字串）
                    if isinstance(output, dict):
                        return output.get(key, [])
                    return json.loads(output).get(key, [])
                except json.JSONDecodeError:
                    pass
        return []

    def image_click(self, image_path: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """图像识别点击。

        Args:
            image_path: 图片路径。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        params = self._image_params(kwargs)
        if "click_duration" in kwargs:
            params["click_duration"] = kwargs["click_duration"]
        return self._exec("image_click",
            {"image_base64": image_base64, **params},
            {"image_path": image_path, **kwargs},
            window=window)

    def image_wait(self, image_path: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """等待图像出现。

        Args:
            image_path: 图片路径。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("image_wait",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs},
            window=window)

    def image_assert(self, image_path: str, negate: bool = False, window_class: Optional[str] = None, **kwargs) -> dict:
        """断言图像存在或不存在（单次截图断言）。

        Args:
            image_path: 图片路径。
            negate: 断言不存在，True 时断言图像不存在。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            confidence: 匹置信度（0-1），默认 0.8。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("image_assert",
            {"image_base64": image_base64, "negate": negate, **self._image_params(kwargs)},
            {"image_path": image_path, "negate": negate, **kwargs},
            window=window)

    def image_click_near_text(self, image_path: str, text: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """点击文本附近最近的图像。

        Args:
            image_path: 图片路径。
            text: 文本内容。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            max_distance: 最大搜索距离（像素），默认 500。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
        """
        window = self._build_window(window_class)
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        params = self._image_params(kwargs)
        if "click_duration" in kwargs:
            params["click_duration"] = kwargs["click_duration"]
        return self._exec("image_click_near_text",
            {"image_base64": image_base64, "value": text, "end_x": kwargs.get("max_distance", 500), **params},
            {"image_path": image_path, "text": text, **kwargs},
            window=window)

    def image_move(self, image_path: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """图像识别后移动鼠标（仅桌面端支持）。

        Args:
            image_path: 图片路径。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 移动偏移量 {"x": 0, "y": 0}。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("image_move",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs},
            window=window)

    def image_double_click(self, image_path: str, window_class: Optional[str] = None, **kwargs) -> dict:
        """图像识别后双击。

        Args:
            image_path: 图片路径。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            index: 选择第几个匹配结果（从 0 开始）。
            offset: 点击偏移量 {"x": 0, "y": 0}。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        window = self._build_window(window_class)
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec("image_double_click",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs},
            window=window)

    def image_exist(self, image_path: str, window_class: Optional[str] = None, **kwargs) -> bool:
        """检查图像是否存在。

        Args:
            image_path: 图片路径。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            index: 选择第几个匹配结果（从 0 开始）。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。

        Returns:
            True 如果图像存在，False 如果不存在。不抛异常。
        """
        window = self._build_window(window_class)
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec_bool("image_exist",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs},
            window=window)

    def image_get_position(self, image_path: str, window_class: Optional[str] = None, **kwargs) -> list:
        """获取图像坐标列表。

        Args:
            image_path: 图片路径。
            window_class: 窗口类名（仅 Windows 平台，精确匹配）。
            timeout: 超时时间（秒），默认 5。
            confidence: 匹置信度（0-1），默认 0.8。
            region: 操作区域名称或坐标 [x1, y1, x2, y2]。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。

        Returns:
            坐标列表 [[x1, y1], [x2, y2], ...]。
        """
        window = self._build_window(window_class)
        image_base64 = self._load_image_as_base64(image_path)
        if not image_base64:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        return self._exec_list("image_get_position",
            {"image_base64": image_base64, **self._image_params(kwargs)},
            {"image_path": image_path, **kwargs},
            window=window)

    def click(self, x: int, y: int, **kwargs) -> dict:
        """坐标点击。

        Args:
            x: X 坐标。
            y: Y 坐标。
            click_duration: 点击持续时间（毫秒），用于长按。0=普通点击，>0=长按指定时间。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        action_data = {"x": x, "y": y}
        if "click_duration" in kwargs:
            action_data["click_duration"] = kwargs["click_duration"]
        if "level" in kwargs:
            action_data["level"] = kwargs["level"]
            if "monitor" in kwargs:
                action_data["monitor"] = kwargs["monitor"]
        return self._exec("click", action_data, {"x": x, "y": y, **kwargs})

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

    def right_click(self, x: int, y: int, **kwargs) -> dict:
        """右键点击指定坐标（仅桌面端）。

        Args:
            x: X 坐标。
            y: Y 坐标。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。

        Note:
            仅 Windows/Mac 桌面端支持，移动端不支持右键操作。
        """
        action_data = {"x": x, "y": y}
        if "level" in kwargs:
            action_data["level"] = kwargs["level"]
            if "monitor" in kwargs:
                action_data["monitor"] = kwargs["monitor"]
        return self._exec("right_click", action_data, {"x": x, "y": y, **kwargs})

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
            duration: 滑动持续时间（毫秒），默认使用 steps 参数控制。
            steps: 滑动步数，控制轨迹平滑度。默认 5 实现平滑滑动。
                - steps 越大，轨迹越平滑，接近真实手指滑动
                - Android: 1 步约 5ms，steps=10 总耗时约 50ms
                - iOS: WDA 不支持 steps 参数，始终使用 duration
        """
        action_data = {"from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}}
        if "duration" in kwargs:
            action_data["duration"] = kwargs["duration"]
        if "steps" in kwargs:
            action_data["steps"] = kwargs["steps"]
        return self._exec("swipe", action_data,
            {"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y, **kwargs})

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int, **kwargs) -> dict:
        """拖拽操作。

        Args:
            from_x: 起点 X 坐标。
            from_y: 起点 Y 坐标。
            to_x: 终点 X 坐标。
            to_y: 终点 Y 坐标。
            duration: 拖拽持续时间（毫秒）。
            steps: 拖拽步数，控制轨迹平滑度。

        Note:
            参数与 swipe 完全一致，可根据语义选用。
        """
        return self.swipe(from_x, from_y, to_x, to_y, **kwargs)

    def input_text(self, x: int, y: int, text: str) -> dict:
        """在指定坐标输入文本。

        Args:
            x: X 坐标。
            y: Y 坐标。
            text: 要输入的文本。
        """
        return self._exec("input", {"x": x, "y": y, "text": text}, {"x": x, "y": y, "text": text})

    def paste_text(self, text: str) -> dict:
        """直接粘贴文本（使用剪贴板 Ctrl+V）。

        Args:
            text: 要粘贴的文本内容。

        Note:
            使用剪贴板方式粘贴，不点击坐标。
            需要先将焦点定位到输入位置（如通过 ocr_click 点击输入框）。
        """
        return self._exec("paste", {"text": text}, {"text": text})

    # ── 其他动作 ─────────────────────────────────────────

    def press(self, key: str, **kwargs) -> dict:
        """按键操作。

        Args:
            key: 按键名称，如 Enter、Escape。
            level: 执行层级（仅 Web），browser 或 system。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。
        """
        action_data = {"key": key}
        if "level" in kwargs:
            action_data["level"] = kwargs["level"]
            if "monitor" in kwargs:
                action_data["monitor"] = kwargs["monitor"]
        return self._exec("press", action_data, {"key": key, **kwargs})

    def wait(self, duration: float) -> dict:
        """固定等待。"""
        duration_ms = int(duration * 1000)
        return self._exec("wait", {"value": str(duration_ms)}, {"duration_ms": duration_ms})

    def start_app(self, app_id: str, proxy: Optional[str] = None) -> dict:
        """启动应用。

        Args:
            app_id: 应用标识。
                - Web: 浏览器类型，如 "chromium"、"firefox"、"webkit"
                - Android: 应用包名，如 "com.example.app"
                - iOS: Bundle ID，如 "com.example.app"
            proxy: 代理配置（仅 Web 平台），格式：
                - "http://user:pass@proxy.example.com:8080"（带认证）
                - "http://proxy.example.com:8080"（无认证）
                - 不传 proxy 参数则显式禁用代理（不走系统代理）

        Note:
            Web 平台专用 proxy 参数，用于测试需要代理访问的内部网站。
        """
        action_data = {"value": app_id}
        if proxy:
            action_data["proxy"] = proxy
        return self._exec("start_app", action_data, {"app_id": app_id, "proxy": proxy})

    def stop_app(self, app_id: str) -> dict:
        """关闭应用。"""
        return self._exec("stop_app", {"value": app_id}, {"app_id": app_id})

    def navigate(self, url: str) -> dict:
        """导航到 URL（Web 端专用）。"""
        return self._exec("navigate", {"value": url}, {"url": url})

    def new_page(self) -> dict:
        """创建新空白标签页（Web 端专用）。

        创建空白新标签页，自动切换焦点到新页面。
        """
        return self._exec("new_page", {}, {})

    def switched_page(self, page_index: int) -> dict:
        """切换到指定页面（Web 端专用）。"""
        return self._exec("switched_page", {"value": str(page_index)}, {"page_index": page_index})

    def close_page(self) -> dict:
        """关闭当前页面（Web 端专用）。"""
        return self._exec("close_page", {}, {})

    def cmd_exec(self, command: str, **kwargs) -> dict:
        """在宿主机执行命令。"""
        timeout_ms = kwargs.get("timeout", 30) * 1000
        return self._exec("cmd_exec",
            {"value": command, "timeout": timeout_ms},
            {"command": command, **kwargs})

    def activate_window(self, value: str, match_by: str = "title", name: Optional[str] = None) -> dict:
        """激活窗口（Windows/Mac/Web 平台支持）。

        将指定窗口带到前台并获取焦点。

        Args:
            value: 窗口标题或窗口类名。
                - title 模式：窗口标题包含匹配（如 "计算器"）
                - class 模式：窗口类名（如 "Chrome_WidgetWin_1"、"Notepad"）
            match_by: 窗口定位方式，默认 title。
                - title: 按窗口标题匹配（包含匹配）
                - class: 按窗口类名匹配（精确匹配）
            name: 进程 exe 名称过滤（可选），用于区分同名窗口类但不同进程的窗口。
                - 如 "chrome.exe"、"msedge.exe"、"notepad.exe"
                - 使用场景：Chrome_WidgetWin_1 是 Chrome 和 Edge 共用的窗口类名，
                  传 name="chrome.exe" 可确保只激活 Chrome 窗口。

        Note:
            平台支持：
            - Windows/Web: 支持 title 和 class 模式
            - Mac: 仅支持 class 模式（通过应用名激活）
        """
        action_data = {"value": value, "match_by": match_by}
        if name:
            action_data["name"] = name
        return self._exec("activate_window", action_data, {"value": value, "match_by": match_by, "name": name})

    def screenshot(self, **kwargs) -> str:
        """截图并返回 base64。

        Args:
            level: 执行层级（仅 Web），browser 或 system。system 可截取原生对话框。
            monitor: 显示器编号（仅 Web，配合 level: system），1=主屏幕，2=副屏幕。

        Returns:
            截图的 base64 编码，失败返回空字符串。
        """
        # 公共 AW 继承 User 的平台
        platform = self.PLATFORM
        if platform == "common" and self.user:
            platform = self.user.platform

        user_id = self.user.user_id if self.user else None
        # iOS/Android 需要传递 device_id
        device_id = None
        if platform in ("ios", "android") and self.user:
            device_id = self.user.device_id

        action_data = {
            "action_type": "screenshot",
            "value": f"screenshot_{int(time.time() * 1000)}",
        }
        if "level" in kwargs:
            action_data["level"] = kwargs["level"]
            if "monitor" in kwargs:
                action_data["monitor"] = kwargs["monitor"]
        # 直接调用 execute 以传递 user_id 和 device_id
        result = self.client.execute(platform, [action_data], user_id=user_id, device_id=device_id)
        if result.get("status") == "success" and result.get("actions"):
            action = result["actions"][0]
            # 优先取 screenshot 字段，其次取 output 字段
            return action.get("screenshot") or action.get("output", "")
        return ""

    # ── Windows 系统控制动作 ────────────────────────────────────────

    def set_resolution(self, width: int, height: int, monitor_index: int = 0) -> dict:
        """设置显示器分辨率（仅 Windows 平台）。

        用于测试不同分辨率下的 UI 表现。

        Args:
            width: 分辨率宽度，如 1920、1280。
            height: 分辨率高度，如 1080、720。
            monitor_index: 显示器索引，默认 0（主显示器）。
                - 0: 主显示器
                - 1: 第二个显示器
                - 2: 第三个显示器

        Note:
            仅 Windows 平台支持。
        """
        action_data = {
            "width": width,
            "height": height,
            "monitor_index": monitor_index,
        }
        return self._exec("set_resolution", action_data,
            {"width": width, "height": height, "monitor_index": monitor_index})

    def set_volume(self, value: int) -> dict:
        """设置系统音量（仅 Windows 平台）。

        Args:
            value: 音量百分比（0-100）。

        Note:
            仅 Windows 平台支持。
        """
        return self._exec("set_volume", {"value": value}, {"value": value})

    def audio_device(self, device: str, state: str) -> dict:
        """启用/停用音频设备（仅 Windows 平台）。

        Args:
            device: 音频设备名称（支持包含匹配），如 "扬声器"、"Realtek Audio"。
                也可传入完整设备 ID。
            state: 设备状态。
                - enable: 启用音频设备
                - disabled: 停用音频设备

        Note:
            仅 Windows 平台支持。
        """
        action_data = {"device": device, "state": state}
        return self._exec("audio_device", action_data, {"device": device, "state": state})