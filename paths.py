# -*- coding: utf-8 -*-
"""路径解析：兼容源码运行与 PyInstaller 打包（frozen）。

源码运行：一切以本文件所在目录为准。
打包运行：config.json 等用户文件放 exe 旁边；WinDivert 二进制
在 PyInstaller 的解包目录（_MEIPASS）里的 vendored/ 下。
"""
import os
import sys

if getattr(sys, "frozen", False):
    APPDIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLED = getattr(sys, "_MEIPASS", APPDIR)
else:
    APPDIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLED = APPDIR

VENDORED_DIR = os.path.join(BUNDLED, "vendored")
# 驱动文件用马甲名（WinDivert 官方支持 dll/sys 同名重命名），
# 避免被安全软件按文件名特征拦截
WINDIVERT_DLL = os.path.join(VENDORED_DIR, "tjnet.dll")
WINDIVERT_SYS = os.path.join(VENDORED_DIR, "tjnet.sys")
CONFIG_PATH = os.path.join(APPDIR, "config.json")
