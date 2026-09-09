# -*- coding: utf-8 -*-
"""托盘行为测试：隐藏到托盘后窗口应 withdraw，恢复后应 deiconify。
用法: python tests/test_tray.py <输出文件>"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "tray.out")
lines = []


def log(m):
    lines.append(m)
    print(m, flush=True)


def main():
    from gui import App
    app = App()
    results = {}

    def step1():
        app._hide_to_tray()

    def step2():
        results["hidden"] = app.state() == "withdrawn"
        results["tray_obj"] = app.tray is not None
        app._restore_from_tray()

    def step3():
        results["restored"] = app.state() == "normal"
        log("hidden=%s tray_obj=%s restored=%s"
            % (results.get("hidden"), results.get("tray_obj"),
               results.get("restored")))
        log("RESULT: %s" % ("PASS" if all(results.values()) else "FAIL"))
        app._quit_app()

    app.after(800, step1)
    app.after(1800, step2)
    app.after(2600, step3)
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    finally:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
