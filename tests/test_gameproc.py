# -*- coding: utf-8 -*-
"""进程识别 + 端点扫描验证（不需要管理员）。
用法: python tests/test_gameproc.py <输出文件>"""
import os
import socket
import sys
import threading
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import gameproc  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "gameproc.out")
_lines = []


def log(msg):
    _lines.append(msg)
    print(msg, flush=True)


def main():
    # 1. 自建一个回环连接
    srv = socket.socket()
    srv.bind(("127.0.0.1", 9988))
    srv.listen(1)
    threading.Thread(target=lambda: srv.accept(), daemon=True).start()
    cli = socket.socket()
    cli.connect(("127.0.0.1", 9988))

    tcp4, udp4, tcp6, udp6 = gameproc.scan_flows(os.getpid())
    log("scan_flows(自身): TCP=%s UDP=%s" % (sorted(tcp4), sorted(udp4)))
    ok1 = ("127.0.0.1", 9988) in tcp4

    # 2. 窗口标题匹配
    root = tk.Tk()
    root.title("fishproc-test-magic")
    root.geometry("1x1")
    root.update()
    cands = gameproc.find_processes(["fishproc-test-magic"])
    log("find_processes: %s" % (cands,))
    ok2 = any(c[0] == os.getpid() for c in cands)

    # 3. describe
    log("describe: %s" % gameproc.describe_flows(tcp4, udp4, tcp6, udp6))

    log("RESULT: %s" % ("PASS" if (ok1 and ok2) else "FAIL"))
    root.destroy()


if __name__ == "__main__":
    try:
        main()
    finally:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
