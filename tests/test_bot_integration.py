# -*- coding: utf-8 -*-
"""整链路集成测试：本进程扮演"游戏"（标题 fishfake-test，持有回环 TCP 连接，
全速发数据），另一个提权进程跑 FishBot 对它限速。
服务端按秒统计收包速率，应能看到限速期 ~1KB/s、解限期高速的交替。
用法: python tests/test_bot_integration.py <输出文件>"""
import os
import socket
import sys
import threading
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "fakegame.out")

DURATION = 20.0
_lines = []


def log(msg):
    _lines.append(msg)
    print(msg, flush=True)


def main():
    # --- 服务端：记录 (t, 累计字节) ---
    samples = []

    def echo_server(sock):
        conn, _ = sock.accept()
        total = 0
        t0 = time.monotonic()
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                total += len(data)
                samples.append((time.monotonic() - t0, total))
                conn.sendall(data)
        except OSError:
            pass

    srv = socket.socket()
    srv.bind(("127.0.0.1", 9997))
    srv.listen(1)
    threading.Thread(target=echo_server, args=(srv,), daemon=True).start()

    # --- 可见窗口（供 bot 按标题识别进程） ---
    root = tk.Tk()
    root.title("fishfake-test")
    root.geometry("260x60")

    cli = socket.socket()
    cli.connect(("127.0.0.1", 9997))
    # 必须持续读走回显，否则回环缓冲塞满会和自己的 echo 死锁
    threading.Thread(target=lambda: [cli.recv(1 << 20) for _ in iter(int, 1)],
                     daemon=True).start()

    t_start = time.monotonic()
    sent = 0
    chunk = b"y" * 4096
    next_beat = 5
    while time.monotonic() - t_start < DURATION:
        try:
            sent += cli.send(chunk)
        except OSError as exc:
            log("发送异常 @%.1fs: %r" % (time.monotonic() - t_start, exc))
            break
        if time.monotonic() - t_start >= next_beat:
            log("进度 %.0fs: 已发送 %.1f KB" % (next_beat, sent / 1024.0))
            next_beat += 5
        root.update()  # 保持窗口消息循环，让 EnumWindows 能看到标题

    time.sleep(0.5)  # 等服务端记录齐
    root.destroy()

    if not samples:
        log("RESULT: FAIL (服务端没有收到数据)")
        return

    # --- 服务端按秒统计收包增量 ---
    rates = {}
    for sec in range(int(DURATION) + 2):
        start_b = 0
        end_b = 0
        for t, b in samples:
            if t < sec:
                start_b = b
            if t < sec + 1:
                end_b = b
        rates[sec] = (end_b - start_b) / 1024.0

    log("每秒收包速率 KB/s:")
    slow, fast = [], []
    for sec in sorted(rates):
        r = rates[sec]
        tag = ""
        if r <= 3.0:
            tag = " <-- 限速"
            slow.append(sec)
        elif r >= 100:
            tag = " <-- 正常"
            fast.append(sec)
        log("  t=%2ds  %8.2f KB/s%s" % (sec, r, tag))
    log("限速秒: %s  正常秒: %s" % (slow, fast))
    log("共发送 %.1f KB" % (sent / 1024.0))

    ok = len(slow) >= 2 and len(fast) >= 2
    log("RESULT: %s" % ("PASS" if ok else "FAIL"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log("EXCEPTION:\n" + traceback.format_exc())
    finally:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
