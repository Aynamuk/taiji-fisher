# -*- coding: utf-8 -*-
"""托盘行为测试：隐藏到托盘后窗口应不可见，恢复后应重新可见。

PySide6 版判据（与旧 CTk 版不同）：
- 隐藏后 `isVisible()` 为 False，且 `tray.isVisible()` 为 True
- 恢复后 `isVisible()` 为 True
- 页头「最小化到托盘」按钮存在且已启用

用法: python tests/test_tray.py <输出文件>
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "tray.out")
lines = []


def log(m):
    lines.append(m)
    print(m, flush=True)


def main():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    import theme as TH
    from gui import App

    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setStyle("Fusion")
    qapp.setStyleSheet(TH.build_qss())
    qapp.setQuitOnLastWindowClosed(False)

    win = App()
    win.show()
    results = {}

    def step1():
        results["btn_exists"] = hasattr(win, "btn_tray")
        results["btn_enabled"] = bool(win.btn_tray.isEnabled())
        win._hide_to_tray()

    def step2():
        results["hidden"] = not win.isVisible()
        results["tray_visible"] = bool(win.tray is not None
                                       and win.tray.isVisible())
        win._restore_from_tray()

    def step3():
        results["restored"] = bool(win.isVisible())
        log("btn=%s/%s hidden=%s tray=%s restored=%s"
            % (results.get("btn_exists"), results.get("btn_enabled"),
               results.get("hidden"), results.get("tray_visible"),
               results.get("restored")))
        ok = all(results.values())
        log("RESULT: %s" % ("PASS" if ok else "FAIL"))
        win._quit_app()
        qapp.quit()

    QTimer.singleShot(800, step1)
    QTimer.singleShot(1800, step2)
    QTimer.singleShot(2600, step3)
    qapp.exec()


if __name__ == "__main__":
    try:
        main()
    finally:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
