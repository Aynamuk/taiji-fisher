# -*- coding: utf-8 -*-
"""太极炸鱼助手入口。

用法：
  python main.py            -> 图形界面
  python main.py --cli      -> 命令行模式（参数见 --help）

需要管理员权限（WinDivert 驱动），未提权时自动弹 UAC。
"""
import ctypes
import os
import sys

import paths

HERE = paths.APPDIR
os.chdir(HERE)
sys.path.insert(0, HERE)

REQUIRED_FILES = [
    paths.WINDIVERT_DLL,
    paths.WINDIVERT_SYS,
]


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def self_elevate():
    """静默 UAC 提权重启自身。GUI 模式隐藏新控制台。"""
    script = os.path.abspath(sys.argv[0])
    args = " ".join('"%s"' % a for a in sys.argv[1:])
    params = '"%s" %s --elevated' % (script, args)
    show = 1 if "--cli" in sys.argv else 0  # SW_SHOWNORMAL / SW_HIDE
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, show)
    if ret <= 32:
        sys.stderr.write("提权失败，请右键『以管理员身份运行』。\n")
        sys.exit(1)
    sys.exit(0)


def check_vendored():
    missing = [p for p in REQUIRED_FILES if not os.path.isfile(p)]
    if missing:
        msg = ("缺少运行库文件:\n  %s\n请确认 vendored 目录完整"
               "(tjnet.dll / tjnet.sys)。" % "\n  ".join(missing))
        sys.stderr.write(msg + "\n")
        if getattr(sys, "frozen", False) or sys.stdout is None:
            ctypes.windll.user32.MessageBoxW(0, msg, "太极炸鱼助手", 0x10)
        sys.exit(1)


def main():
    if "--elevated" not in sys.argv:
        if not is_admin():
            self_elevate()
    else:
        sys.argv.remove("--elevated")

    # 提权后的新进程工作目录可能是 C:\Windows\System32，重新定位
    os.chdir(HERE)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    check_vendored()

    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        run_cli()
    else:
        from gui import run_gui
        run_gui()


def run_cli():
    import argparse
    import time
    import keyboard

    if sys.stdout is None:  # --windowed 打包没有控制台
        ctypes.windll.user32.MessageBoxW(
            0, "这个 exe 是窗口版，没有控制台。\n命令行模式请用源码方式运行："
               "python main.py --cli ...", "太极炸鱼助手", 0x30)
        return

    parser = argparse.ArgumentParser(description="太极炸鱼助手 CLI")
    parser.add_argument("--keywords", default="yysls",
                        help="进程识别关键字，逗号分隔（默认 yysls）")
    parser.add_argument("--rate-kb", type=float, default=1.0, dest="rate_kb")
    parser.add_argument("--throttle", type=float, default=600.0, dest="throttle")
    parser.add_argument("--release", type=float, default=10.0, dest="release")
    parser.add_argument("--cast-key", default="r", dest="cast_key")
    parser.add_argument("--interval", type=float, default=1.4)
    parser.add_argument("--cycles", type=int, default=0)
    parser.add_argument("--stop-min", type=float, default=0, dest="stop_min",
                        help="定时停止：N 分钟后自动停止任务（0=不停）")
    parser.add_argument("--mode", choices=["foreground", "postmessage"],
                        default="foreground")
    args = parser.parse_args()

    import bot as botmod

    def log(msg, level="info"):
        print("[%s] %s" % (level, msg), flush=True)

    def on_state(state, **kw):
        log("状态 -> %s" % state)

    cfg = {
        "process_keywords": [k.strip() for k in args.keywords.split(",") if k.strip()],
        "rate_bps": args.rate_kb * 1024.0,
        "throttle_seconds": args.throttle,
        "release_seconds": args.release,
        "cast_key": args.cast_key,
        "cast_interval": args.interval,
        "cycles": args.cycles,
        "stop_after_minutes": args.stop_min,
        "input_mode": args.mode,
        "windivert_dll": paths.WINDIVERT_DLL,
    }
    b = botmod.FishBot(cfg, log=log, on_state=on_state)

    def f9():
        if b.is_alive():
            b.toggle_pause()
        else:
            b.start()

    def f12():
        log("F12 紧急解限！", "warn")
        b.stop(emergency=True)

    try:
        keyboard.add_hotkey("f9", f9)
        keyboard.add_hotkey("f10", lambda: b.stop())
        keyboard.add_hotkey("f12", f12)
    except Exception:
        pass

    log("F9 = 开始/暂停，F10 = 停止，F12 = 紧急解限停止。Ctrl+C 退出。")
    b.start()
    try:
        while b.is_alive():
            time.sleep(0.3)
    except KeyboardInterrupt:
        b.stop(emergency=True)
        b.join(timeout=5)
    log("机器人已退出，网络恢复正常")


if __name__ == "__main__":
    main()
