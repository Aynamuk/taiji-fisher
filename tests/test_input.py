# -*- coding: utf-8 -*-
"""按键注入验证：SendInput 前台 + PostMessage 后台。
用法: python tests/test_input.py <输出文件>"""
import ctypes
import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import gameinput  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "input.out")
user32 = ctypes.WinDLL("user32", use_last_error=True)
_lines = []


def log(msg):
    _lines.append(msg)
    print(msg, flush=True)


def make_foreground(hwnd):
    """ALT 技巧绕过前台锁。返回是否成功。"""
    user32.keybd_event(0x12, 0, 0, 0)
    time.sleep(0.05)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.15)
    return user32.GetForegroundWindow() == hwnd


def main():
    root = tk.Tk()
    root.title("fishinput-test")
    root.geometry("420x120")
    entry = tk.Entry(root, width=48, font=("Consolas", 12))
    entry.pack(pady=20, padx=20)
    entry.focus_set()
    root.update()

    top = user32.GetAncestor(entry.winfo_id(), 2)  # GA_ROOT

    # ============ 1. PostMessage 后台（不依赖焦点）============
    gameinput.send_key_postmessage(entry.winfo_id(), "z", 60)
    root.update()
    time.sleep(0.2)
    root.update()
    v_pm = entry.get()
    log("PostMessage 'z' (无焦点) -> Entry = %r  %s"
        % (v_pm, "OK" if v_pm == "z" else "FAIL"))

    # ============ 2. SendInput 前台 ============
    fg_ok = False
    for _ in range(5):
        fg_ok = make_foreground(top)
        if fg_ok:
            break
        time.sleep(0.4)
    log("前台切换: %s" % ("成功" if fg_ok else "失败"))

    v_si = ""
    if fg_ok:
        entry.delete(0, "end")
        root.update()
        # 解除 IME 关联（游戏普遍这么干），避免中文输入法截获字母键
        imm32 = ctypes.WinDLL("imm32")
        imm32.ImmAssociateContext(entry.winfo_id(), None)
        entry.focus_force()
        root.update()
        time.sleep(0.2)
        root.bind("<Key>", lambda e: log("  tk收到事件: keysym=%r char=%r vk=0x%X"
                                         % (e.keysym, e.char, e.keycode)))
        gameinput.send_key_foreground("a", 45)
        root.update()
        time.sleep(0.1)
        root.update()
        v_si = entry.get()
        root.unbind("<Key>")
        log("SendInput 'a' (前台=自己) -> Entry = %r  %s"
            % (v_si, "OK" if v_si == "a" else "FAIL"))
    else:
        log("SendInput 跳过（无法前置窗口）")

    # ============ 3. 系统层验证（不依赖任何窗口）============
    inp = gameinput.INPUT()
    inp.type = 1
    inp.ki = gameinput.KEYBDINPUT(0x41, 0x1E, 0, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(gameinput.INPUT()))
    time.sleep(0.1)
    down = bool(user32.GetAsyncKeyState(0x41) & 0x8000)
    inp.ki = gameinput.KEYBDINPUT(0x41, 0x1E, 2, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(gameinput.INPUT()))
    log("GetAsyncKeyState 注入按下期间 = %s (应为 True)" % down)

    log("RESULT: %s" % ("PASS" if (v_pm == "z" and v_si == "a" and down) else
                         ("PARTIAL" if (v_pm == "z" and down) else "FAIL")))
    root.destroy()


if __name__ == "__main__":
    try:
        main()
    finally:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
