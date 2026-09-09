# -*- coding: utf-8 -*-
"""FlowShaper 回环限速验证。需管理员权限。
用法: python tests/test_throttle.py <输出文件>"""
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from throttler import FlowShaper  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "throttle.out")
_lines = []


def log(msg, level="info"):
    _lines.append(msg)
    print(msg, flush=True)


def echo_server(sock):
    conn, _ = sock.accept()
    conn.settimeout(None)
    try:
        while True:
            data = conn.recv(65536)
            if not data:
                break
            conn.sendall(data)
    except OSError:
        pass
    finally:
        conn.close()


def pump(sock, total):
    """发送 total 字节并等回显收齐，返回耗时。"""
    got = [0]

    def reader():
        while got[0] < total:
            d = sock.recv(65536)
            if not d:
                break
            got[0] += len(d)

    t_read = threading.Thread(target=reader, daemon=True)
    t_read.start()
    t0 = time.perf_counter()
    sent = 0
    chunk = b"x" * 4096
    while sent < total:
        sent += sock.send(chunk)
    t_read.join(timeout=120)
    return time.perf_counter() - t0, sent


def main():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 9999))
    srv.listen(1)
    t = threading.Thread(target=echo_server, args=(srv,), daemon=True)
    t.start()

    cli = socket.socket()
    cli.connect(("127.0.0.1", 9999))
    cli.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    N = 4 * 1024 * 1024      # 基线/解限用大流量
    N_THR = 60 * 1024        # 限速期用小流量（10KB/s 下约 6 秒）

    t0, _ = pump(cli, N)
    base = N / t0
    log("基线速率      : %.0f KB/s (%.1fms)" % (base / 1024, t0 * 1000))

    shaper = FlowShaper(os.path.join(ROOT, "vendored", "tjnet.dll"),
                        10 * 1024, log=log)
    variant = "both"
    if "--out-only" in sys.argv:
        variant = "out"
    elif "--in-only" in sys.argv:
        variant = "in"
    if variant == "out":
        shaper.start({("127.0.0.1", 9999)}, set(),
                     filter_override="(outbound and tcp and "
                                     "ip.DstAddr == 127.0.0.1 and "
                                     "tcp.DstPort == 9999)")
    elif variant == "in":
        shaper.start({("127.0.0.1", 9999)}, set(),
                     filter_override="(inbound and tcp and "
                                     "ip.SrcAddr == 127.0.0.1 and "
                                     "tcp.SrcPort == 9999)")
    else:
        shaper.start({("127.0.0.1", 9999)}, set())
    log("变体: %s" % variant)
    time.sleep(0.3)
    t1, _ = pump(cli, N_THR)
    throttled = N_THR / t1
    log("限速后速率    : %.2f KB/s (目标 10)" % (throttled / 1024))
    st = shaper.stats()
    log("统计: %r" % st)
    shaper.stop(flush=True)

    time.sleep(0.3)
    t2, _ = pump(cli, N)
    after = N / t2
    log("解限后速率    : %.0f KB/s" % (after / 1024))

    ok_base = base > 100 * 1024
    ok_throttle = 4 * 1024 < throttled < 20 * 1024
    ok_after = after > 100 * 1024
    log("基线>100KB/s  : %s" % ok_base)
    log("限速≈10KB/s   : %s" % ok_throttle)
    log("解限恢复>100  : %s" % ok_after)
    log("RESULT: %s" % ("PASS" if (ok_base and ok_throttle and ok_after) else "FAIL"))

    cli.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log("EXCEPTION:\n" + traceback.format_exc())
    finally:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
