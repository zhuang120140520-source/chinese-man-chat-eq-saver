# -*- coding: utf-8 -*-
"""Only an explicit button request can open a capture session or run OCR."""
import ctypes
import time
import numpy as np
from app import chatapps
from app.capture import Capture, chat_area, unminimize
from app.ocr import Reader, read_title


def _packet(full, area, title, reader, lines):
    k = max(1, -(-max(full.shape[:2]) // 1100))
    small = np.ascontiguousarray(full[::k, ::k])
    return {"w": small.shape[1], "h": small.shape[0], "rgb": small.tobytes(), "scale": k,
            "area": tuple(int(v) for v in area[:4]) if area else None,
            "pane_top": int(area[5]) if area else 0, "title": title,
            "boxes": reader.last_boxes if reader else [],
            "lines": [(w, n, t) for w, n, t, _ in lines],
            "ocr_ms": reader.last_ms if reader else 0, "ts": time.time()}


def read_frame(full, readers, app, previous_title="", require_title=False, title_cache=None):
    area = chat_area(full)
    if area is None:
        raise ValueError("消息区认不出来，请放大微信窗口")
    x0, y0, x1, y1, bg, y_pane = area
    header = full[y_pane:y0, x0:x1]
    if not require_title and title_cache and np.array_equal(header, title_cache.get("header")):
        name = title_cache["name"]
    else:
        name = read_title(header, app)
        if title_cache is not None:
            title_cache.update(header=header.copy(), name=name)
    if require_title and not name:
        raise ValueError("会话名称未识别清楚，请重试截图")
    # A manual request must verify the exact current title, without fuzzy contact matching.
    title = name or previous_title or "当前会话"
    if title not in readers:
        readers[title] = Reader(app)
    reader = readers[title]
    lines = reader.read(full[y0:y1, x0:x1], bg)
    visible, new = reader.observe(lines)
    return title, area, reader, lines, visible, new


def run(q, debug_on, commands):
    ctypes.windll.user32.SetProcessDPIAware()
    readers = {}
    while True:
        request = commands.get()  # Idle indefinitely without capturing or reading.
        if request[0] == "stop":
            return
        if request[0] != "snapshot":
            continue
        _, request_id, hwnd, app_key = request
        q.put(("snapshot_status", request_id, "正在截图…"))
        cap = None
        try:
            unminimize(hwnd)
            cap = Capture(hwnd)
            try:
                full = cap.snapshot()
            finally:
                cap.stop()  # No further frames while OCR, selection or generation runs.
                cap = None
            q.put(("snapshot_status", request_id, "正在识别当前画面…"))
            title, area, reader, lines, visible, _new = read_frame(
                full, readers, chatapps.get(app_key), require_title=True)
            rect = tuple(int(v) for v in area[:4])
            q.put(("snapshot", request_id, title, visible, rect, reader.last_ms))
            if debug_on.is_set():
                q.put(("debug", _packet(full, area, title, reader, lines)))
        except Exception as e:
            detail = str(e) if isinstance(e, ValueError) else "截图识别失败，请保持微信窗口可见后重试"
            q.put(("snapshot_error", request_id, detail))
        finally:
            if cap is not None:
                cap.stop()
