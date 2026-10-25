# -*- mode: python ; coding: utf-8 -*-
# PySide6 走 PyInstaller 内置 hook，无需 collect_all。
# 但默认会把 Qt 全家桶（WebEngine / 3D / Multimedia / QML 等）全打进来，
# 体积会从 ~30MB 涨到 200MB+，这里用 excludes 裁到只留 QtWidgets 所需。

datas = [('assets/icon.ico', 'assets'),
         ('assets/icon_src.png', 'assets')]

# WinDivert64.sys 必须打进去：dll 内部把驱动文件名写死成 WinDivert64.sys，
# 只有 tjnet.sys 时 WinDivertOpen 会报 WinError 2（找不到驱动）
binaries = [('vendored/tjnet.dll', 'vendored'),
            ('vendored/tjnet.sys', 'vendored'),
            ('vendored/WinDivert64.sys', 'vendored')]

hiddenimports = []

excludes = [
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets',
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
    'PySide6.QtQuick3D', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
    'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning',
    'PySide6.QtSerialPort', 'PySide6.QtSerialBus', 'PySide6.QtSql',
    'PySide6.QtTest', 'PySide6.QtDesigner', 'PySide6.QtHelp',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtRemoteObjects',
    'PySide6.QtScxml', 'PySide6.QtSensors', 'PySide6.QtStateMachine',
    'PySide6.QtTextToSpeech', 'PySide6.QtUiTools', 'PySide6.QtSpatialAudio',
    'customtkinter', 'pystray', 'darkdetect', 'tkinter', '_tkinter',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TaijiFisher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon='assets/icon.ico',
)
