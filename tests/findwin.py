# -*- coding: utf-8 -*-
"""枚举顶层窗口，打印标题含关键字的窗口矩形。"""
import ctypes
import ctypes.wintypes

u32 = ctypes.WinDLL("user32")
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
res = []


def cb(h, _):
    buf = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(h, buf, 256)
    if buf.value:
        r = ctypes.wintypes.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        res.append((buf.value, r.left, r.top, r.right, r.bottom))
    return True


u32.EnumWindows(CB(cb), 0)
for t, l, tp, rt, b in res:
    if "太极" in t:
        print("title=%r L=%d T=%d R=%d B=%d" % (t, l, tp, rt, b))
