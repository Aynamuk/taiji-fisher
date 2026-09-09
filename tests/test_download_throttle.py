# -*- coding: utf-8 -*-
"""真实网卡下载限速验证（需管理员）。

持续循环用 curl 从 npmmirror 下载 26MB 文件（下完自动重来），
ThrottleSession 仅限速下载方向 500KB/s，每 3 秒重扫端点。
判定：取第 12~40 秒窗口内限速器的放行速率，应 ≈ 500KB/s。
用法: python tests/test_download_throttle.py <输出文件>
"""
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import gameproc  # noqa: E402
import throttler  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "dl.out")
CURL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32",
                    "curl.exe")
URL = "https://registry.npmmirror.com/-/binary/python/3.11.9/python-3.11.9-amd64.exe"
_lines = []
procs = []


def log(msg, level="info"):
    _lines.append(msg)
    print(msg, flush=True)


def main():
    if not os.path.isfile(CURL):
        log("RESULT: FAIL (没有 curl.exe)")
        return

    # 1. 基线：单次下载测瞬时速率
    p = subprocess.Popen(
        [CURL, "-sS", "-L", "-o", "NUL", "--max-time", "8",
         "-w", "%{size_download} %{speed_download}", URL],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        out, _ = p.communicate(timeout=15)
        base = float(out.decode("utf-8", "replace").strip().split()[-1])
    except Exception:
        base = 0
    log("基线速率      : %.0f KB/s" % (base / 1024))

    # 2. 持续下载 + 仅下载方向限速 500KB/s
    session = throttler.ThrottleSession(
        os.path.join(ROOT, "vendored", "tjnet.dll"), 500 * 1024, log=log)
    done = [False]

    def downloader():
        while not done[0]:
            pr = subprocess.Popen(
                [CURL, "-sS", "-L", "-o", "NUL", "--max-time", "30", URL],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            procs.append(pr)
            try:
                pr.wait(timeout=30)
            except Exception:
                pr.kill()

    dt = threading.Thread(target=downloader, daemon=True)
    dt.start()

    def refresher():
        while not done[0]:
            try:
                sets = [gameproc.scan_flows(proc[0])
                        for proc in gameproc.find_processes(["curl"])]
                t4 = set().union(*[s[0] for s in sets]) if sets else set()
                u4 = set().union(*[s[1] for s in sets]) if sets else set()
                t6 = set().union(*[s[2] for s in sets]) if sets else set()
                u6 = set().union(*[s[3] for s in sets]) if sets else set()
                if t4 or u4 or t6 or u6:
                    session.update(t4, u4, t6, u6)
            except Exception:
                pass
            time.sleep(3)

    rt = threading.Thread(target=refresher, daemon=True)
    rt.start()

    # 预热 5 秒（等首个包捕获），然后取 12 秒窗口的放行速率
    time.sleep(5)
    s1 = session.stats()
    t1 = time.monotonic()
    time.sleep(12)
    s2 = session.stats()
    t2 = time.monotonic()
    done[0] = True
    dt.join(timeout=35)
    rt.join(timeout=5)

    window = t2 - t1
    rate = (s2["in_sent"] - s1["in_sent"]) / window if window else 0
    log("限速统计      : %r" % s2)
    log("窗口放行速率  : %.1f KB/s (目标 500)" % (rate / 1024))

    session.release()

    # 3. 解除验证
    p = subprocess.Popen(
        [CURL, "-sS", "-L", "-o", "NUL", "--max-time", "8",
         "-w", "%{size_download} %{speed_download}", URL],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        out, _ = p.communicate(timeout=15)
        after = float(out.decode("utf-8", "replace").strip().split()[-1])
    except Exception:
        after = 0
    log("解限后速率    : %.0f KB/s" % (after / 1024))

    ok = (base > 500 * 1024
          and 350 * 1024 < rate < 700 * 1024
          and s2.get("recv_alive")
          and after > 500 * 1024)
    log("RESULT: %s" % ("PASS" if ok else "FAIL"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log("EXCEPTION:\n" + traceback.format_exc())
    finally:
        for pr in procs:
            try:
                pr.kill()
            except Exception:
                pass
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
