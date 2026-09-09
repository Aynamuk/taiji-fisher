# -*- coding: utf-8 -*-
"""用 PrintWindow 离屏抓取太极炸鱼助手窗口（窗口被遮挡也能抓）。

用法: python tests/grab_gui.py [输出路径]
默认输出 docs/gui_preview.png。约定：每次改动 GUI 后重新生成预览图。
PrintWindow 失败时自动兜底：切前台 + 全屏截图按窗口矩形裁剪。
"""
import ctypes
import ctypes.wintypes
import os
import sys
import time

ctypes.windll.user32.SetProcessDPIAware()

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "gui_preview.png")
ctypes.windll.user32.SetProcessDPIAware()

u32 = ctypes.WinDLL("user32")
g32 = ctypes.WinDLL("gdi32")
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
target = []


def cb(h, _):
    buf = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(h, buf, 256)
    if "太极炸鱼助手" in buf.value:
        target.append(h)
    return True


u32.EnumWindows(CB(cb), 0)
assert target, "没找到窗口"
hwnd = target[0]

r = ctypes.wintypes.RECT()
u32.GetWindowRect(hwnd, ctypes.byref(r))
w, h = r.right - r.left, r.bottom - r.top

hdc_win = u32.GetWindowDC(hwnd)
mem = g32.CreateCompatibleDC(hdc_win)
bmp = g32.CreateCompatibleBitmap(hdc_win, w, h)
g32.SelectObject(mem, bmp)
# PW_RENDERFULLCONTENT = 2：让窗口离屏重绘
ok = u32.PrintWindow(hwnd, mem, 2)

class BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]
class BMI(ctypes.Structure):
    _fields_ = [("bmiHeader", BMIH), ("bmiColors", ctypes.c_uint32 * 3)]

from PIL import Image, ImageGrab

img = None
if ok:
    bmi = BMI()
    bmi.bmiHeader.biSize = ctypes.sizeof(BMIH)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)
else:
    # PrintWindow 失败的兜底：切到前台后抓屏幕再按窗口矩形裁剪
    u32.keybd_event(0x12, 0, 0, 0)
    time.sleep(0.05)
    u32.SetForegroundWindow(hwnd)
    u32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.6)
    shot = ImageGrab.grab()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    img = shot.crop((max(0, r.left), max(0, r.top),
                     min(shot.width, r.right), min(shot.height, r.bottom)))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT)
print("ok=%s size=%dx%d -> %s" % (ok, img.width, img.height, OUT))
