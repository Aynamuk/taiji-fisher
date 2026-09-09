# -*- coding: utf-8 -*-
"""探针：对 fishfake-test 进程直接用 ThrottleSession 限速 6 秒，打印 stats。
用法（提权）: python tests/probe_session.py"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import gameproc  # noqa: E402
import throttler  # noqa: E402

cands = gameproc.find_processes(["fishfake"])
print("candidates:", cands, flush=True)
pid = cands[0][0]
tcp4, udp4, tcp6, udp6 = gameproc.scan_flows(pid)
print("flows:", tcp4, udp4, tcp6, udp6, flush=True)

s = throttler.ThrottleSession(os.path.join(ROOT, "vendored", "tjnet.dll"),
                              1024.0, log=print)
s.update(tcp4, udp4, tcp6, udp6)
print("filter:", s._shaper.filter if s._shaper else None, flush=True)
time.sleep(6)
print("stats:", s.stats(), flush=True)
s.release()
print("after release:", s.stats(), flush=True)
