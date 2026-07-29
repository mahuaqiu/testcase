# -*- coding: utf-8 -*-
"""验证 V2 报告生成器的临时脚本：用模拟日志数据生成一份报告。"""

import base64
import io
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.report_generator import HTMLReportGenerator


def make_png_base64(r, g, b, w=320, h=200):
    """生成纯色 PNG 的 base64（模拟截图）。"""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes([r, g, b]) * w for _ in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    return base64.b64encode(png).decode()


SHOT_A = make_png_base64(180, 200, 230)
SHOT_B = make_png_base64(230, 190, 190)

U_A = {"user_id": "userA", "user_name": "张三", "user_account": "138****2211", "user_ip": "10.8.3.21"}
U_B = {"user_id": "userB", "user_name": "李四", "user_account": "139****8822", "user_ip": "10.8.3.35"}
U_API = {"user_id": "userA_api", "user_name": "张三", "user_account": "138****2211", "user_ip": ""}

logs = []


def aw(t, aw_name, method, args, success=True, dur=500, result=None, biz=False,
       call_id="", pid="", disp="", pdisp="", parent_aw="", req="", target_image=""):
    logs.append({
        "time": t, "type": "aw_call", "aw_name": aw_name, "method": method,
        "args": args, "success": success,
        "result": result or {"status": "success" if success else "failed", "output": "", "error": ""},
        "duration_ms": dur, "target_image": target_image, "target_image_path": "",
        "parent_aw": parent_aw, "is_business_method": biz, "request_id": req,
        "call_id": call_id, "parent_call_id": pid, "display_name": disp, "parent_display": pdisp,
    })


# ── 阶段：申请资源 ──
logs.append({"time": "14:02:01.334", "type": "step", "step": "申请用户资源",
             "detail": '{\n  "namespace": "meeting-e2e",\n  "users": ["userA", "userB"]\n}'})

# ── 组1：登录系统 userA（同步模式：子操作 + 组头日志在后） ──
CID1 = "c1aaaaaaaaaa"
aw("14:02:03.102", "LoginAW", "app_start", {**U_A, "app_id": "com.meeting.app"}, dur=2100,
   pid=CID1, pdisp="登录系统", parent_aw="LoginAW.do_login")
aw("14:02:05.870", "LoginAW", "ocr_wait", {**U_A, "text": "账号登录", "timeout": 10}, dur=1600,
   pid=CID1, pdisp="登录系统", parent_aw="LoginAW.do_login")
aw("14:02:07.518", "LoginAW", "ocr_click", {**U_A, "text": "账号登录"}, dur=640,
   result={"status": "success", "ocr_info": [
       {"text": "账号登录", "center": {"x": 412, "y": 388}},
       {"text": "验证码登录", "center": {"x": 592, "y": 388}}]},
   pid=CID1, pdisp="登录系统", parent_aw="LoginAW.do_login", req="req-7f3a12")
aw("14:02:08.301", "LoginAW", "ocr_input", {**U_A, "label": "手机号", "content": "138****2211"}, dur=890,
   pid=CID1, pdisp="登录系统", parent_aw="LoginAW.do_login")
aw("14:02:10.377", "LoginAW", "ocr_click", {**U_A, "text": "登录"}, dur=520,
   pid=CID1, pdisp="登录系统", parent_aw="LoginAW.do_login")
aw("14:02:11.020", "LoginAW", "ocr_wait", {**U_A, "text": "工作台", "timeout": 15}, dur=9800,
   pid=CID1, pdisp="登录系统", parent_aw="LoginAW.do_login")
aw("14:02:20.911", "LoginAW", "do_login", U_A, dur=18400, biz=True, call_id=CID1, disp="登录系统")

# ── 组2：创建会议（API AW） ──
CID2 = "c2bbbbbbbbbb"
aw("14:02:23.150", "MeetingApiAW", "api_create_meeting",
   {**U_API, "name": "等候室验证会议", "waiting_room": False}, dur=860,
   pid=CID2, pdisp="创建会议", parent_aw="MeetingApiAW.do_create_meeting")
aw("14:02:24.033", "MeetingApiAW", "api_get_meeting_info", {**U_API, "meeting_id": "982-113-664"}, dur=340,
   pid=CID2, pdisp="创建会议", parent_aw="MeetingApiAW.do_create_meeting")
aw("14:02:24.400", "MeetingApiAW", "do_create_meeting", U_API, dur=1250, biz=True, call_id=CID2, disp="创建会议")

# ── 组3：跨 AW 嵌套 — do_join_as_host 内部调 MeetingControlAW 的原子操作（旧版会孤儿） ──
CID3 = "c3cccccccccc"
aw("14:02:25.108", "MeetingAW", "ocr_click", {**U_A, "text": "加入会议"}, dur=610,
   pid=CID3, pdisp="作为主持人入会", parent_aw="MeetingAW.do_join_as_host")
aw("14:02:26.001", "MeetingControlAW", "ocr_input", {**U_A, "label": "会议号", "content": "982-113-664"}, dur=920,
   pid=CID3, pdisp="作为主持人入会", parent_aw="MeetingAW.do_join_as_host")
aw("14:02:27.780", "MeetingControlAW", "image_wait",
   {**U_A, "image_path": "in_meeting_toolbar.png", "timeout": 30}, dur=8300,
   pid=CID3, pdisp="作为主持人入会", parent_aw="MeetingAW.do_join_as_host")
aw("14:02:56.240", "MeetingAW", "do_join_as_host", U_A, dur=11200, biz=True, call_id=CID3, disp="作为主持人入会")

# ── 组4：parallel 成功场景（无组头日志，仅子操作 → 靠 parent_display 合成组头） ──
CID4 = "c4dddddddddd"
aw("14:03:02.410", "MeetingAW", "app_start", {**U_B, "app_id": "com.meeting.app"}, dur=2400,
   pid=CID4, pdisp="作为访客入会", parent_aw="MeetingAW.do_join_as_guest")
aw("14:03:05.322", "MeetingAW", "ocr_click", {**U_B, "text": "加入会议"}, dur=700,
   pid=CID4, pdisp="作为访客入会", parent_aw="MeetingAW.do_join_as_guest")
aw("14:03:07.240", "MeetingAW", "ocr_click", {**U_B, "text": "加入"}, dur=530,
   pid=CID4, pdisp="作为访客入会", parent_aw="MeetingAW.do_join_as_guest")

# ── 组5：失败组 — 断言在等候室（带错误截图 + OCR + 组头失败日志） ──
CID5 = "c5eeeeeeeeee"
aw("14:03:29.451", "EnterpriseWaitRoomAW", "screenshot", U_B, dur=310,
   pid=CID5, pdisp="断言在等候室", parent_aw="EnterpriseWaitRoomAW.should_in_waitingroom")
aw("14:03:31.377", "EnterpriseWaitRoomAW", "ocr_assert",
   {**U_B, "text": "主持人将稍后准许您进入", "timeout": 20},
   success=False, dur=20100,
   result={"status": "failed",
           "error": 'OCR 断言失败，20s 内未识别到文本 "主持人将稍后准许您进入"。最近一次识别: ["会议加载中", "取消"]',
           "error_screenshot": SHOT_B,
           "ocr_info": [{"text": "会议加载中", "center": {"x": 640, "y": 512}},
                        {"text": "取消", "center": {"x": 640, "y": 780}}]},
   pid=CID5, pdisp="断言在等候室", parent_aw="EnterpriseWaitRoomAW.should_in_waitingroom",
   req="req-b81f4c22")
aw("14:03:51.600", "EnterpriseWaitRoomAW", "should_in_waitingroom", U_B, success=False, dur=20500,
   biz=True, call_id=CID5, disp="断言在等候室",
   result={"status": "failed", "error": "AWError: ocr_assert 执行失败"})

# 另一用户的失败截图（screenshot 类型 → 末尾截图区）
logs.append({"time": "14:03:52.000", "type": "screenshot", "user_id": "userA", "base64": SHOT_A})

# ── 阶段：teardown ──
logs.append({"time": "14:03:52.100", "type": "step", "step": "Teardown · 清理会议与用户资源", "detail": ""})

# ── 孤儿操作（无 parent → "直接操作"兜底组） ──
aw("14:03:52.410", "MeetingApiAW", "api_cancel_meeting", {**U_API, "meeting_id": "982-113-664"}, dur=380)
aw("14:03:52.900", "CommonAW", "app_stop", {**U_A, "app_id": "com.meeting.app"}, dur=450)

report_dir = Path(__file__).parent
report_path = report_dir / "report_v2_generated.html"
HTMLReportGenerator.generate(
    report_path=report_path,
    case_name="test_meeting_waiting_room",
    case_title="验证等候室开启后，访客入会需主持人准入",
    logs=logs,
    duration_ms=161000,
    status="failed",
    error_msg='AWError: EnterpriseWaitRoomAW.ocr_assert 执行失败: OCR 断言失败，20s 内未识别到文本 "主持人将稍后准许您进入"',
    is_api_failure=False,
)
print(f"OK -> {report_path}")
