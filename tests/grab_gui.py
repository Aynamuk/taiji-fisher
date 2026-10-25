# -*- coding: utf-8 -*-
"""生成界面预览图：启动 App → PrintWindow 离屏抓取 → 存 docs/gui_preview.png。

用法: python tests/grab_gui.py [输出路径] [宽] [高]
默认输出 docs/gui_preview.png。约定：每次改动 GUI 后重新生成预览图。
PrintWindow 对 Tk 窗口时好时坏，但对 Qt 窗口稳定；仍保留全黑兜底提示。
"""
import ctypes
import ctypes.wintypes
import os
import sys

ctypes.windll.user32.SetProcessDPIAware()

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "docs", "gui_preview.png")
W = int(sys.argv[2]) if len(sys.argv) > 2 else 960
H = int(sys.argv[3]) if len(sys.argv) > 3 else 660

from PySide6.QtCore import QTimer                       # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402
from PIL import Image                                   # noqa: E402

import theme as TH                                      # noqa: E402
from gui import App                                     # noqa: E402

u32 = ctypes.WinDLL("user32")
g32 = ctypes.WinDLL("gdi32")


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class BMI(ctypes.Structure):
    _fields_ = [("bmiHeader", BMIH), ("bmiColors", ctypes.c_uint32 * 3)]


def grab(hwnd):
    """PW_RENDERFULLCONTENT=2：让窗口在离屏 DC 上重绘，被遮挡也能抓。"""
    r = ctypes.wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = u32.GetWindowDC(hwnd)
    mem = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    g32.SelectObject(mem, bmp)
    ok = u32.PrintWindow(hwnd, mem, 2)
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
    g32.DeleteObject(bmp)
    g32.DeleteDC(mem)
    u32.ReleaseDC(hwnd, hdc)
    return ok, img


def main():
    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(TH.build_qss())
    qapp.setQuitOnLastWindowClosed(False)
    win = App()
    win.resize(W, H)
    win.show()

    def shoot():
        ok, img = grab(int(win.winId()))
        if img.getextrema() == ((0, 0), (0, 0), (0, 0)):
            print("警告: 抓到全黑图，PrintWindow 失败")
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        img.save(OUT)
        print("ok=%s size=%dx%d -> %s" % (ok, img.width, img.height, OUT))
        win._quit_app()
        qapp.quit()

    QTimer.singleShot(1400, shoot)
    qapp.exec()


if __name__ == "__main__":
    main()
