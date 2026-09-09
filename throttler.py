# -*- coding: utf-8 -*-
"""按游戏进程定点限速的流量整形器。

原理：
  1. 用 psutil 找到游戏进程当前所有 TCP 远端端点 (ip, port) 和 UDP 本地端口；
  2. 据此构造 WinDivert 过滤串，只捕获游戏连接的进出包；
  3. 用户态令牌桶按 rate_bps 字节/秒（每个方向独立）放行，其余排队；
  4. 队列超过上限丢新包（TCP 会自动重传，UDP 游戏协议天然容忍丢包）。

停止时可选 flush：以较快速度把排队的包注回，避免一次性大突发。
内核队列中尚未 recv 的包在 Close 时会被丢弃，同样由 TCP 重传兜底。
"""
import ctypes
import queue
import threading
import time
import collections

import windivert

_MTU_BUF = None


def _recv_buffer():
    global _MTU_BUF
    if _MTU_BUF is None:
        _MTU_BUF = (ctypes.c_ubyte * windivert.MTU_MAX)()
    return _MTU_BUF


def build_filter(tcp_flows, udp_ports, tcp_flows6=None):
    """构造 WinDivert 过滤串 —— 只匹配【下载（入站）】方向。

    卡 CD 技巧只需要饿死客户端的下行同步（服务器时间/CD 包），
    上行（施放请求、心跳）保持畅通：服务器持续收到心跳不会踢线，
    施放请求即时到达、下行同步却跟不上，CD 才会卡住。
    tcp_flows: {(ip, port), ...} 远端端点；udp_ports: {port, ...} 本地端口。
    """
    parts = []
    for ip, port in sorted(tcp_flows):
        parts.append("(inbound and tcp and ip.SrcAddr == %s and tcp.SrcPort == %d)"
                     % (ip, port))
    for ip, port in sorted(tcp_flows6 or ()):
        if "%" in ip:
            ip = ip.split("%", 1)[0]
        parts.append("(inbound and tcp and ipv6.SrcAddr == %s and tcp.SrcPort == %d)"
                     % (ip, port))
    for port in sorted(udp_ports):
        parts.append("(inbound and udp and udp.DstPort == %d)" % port)
    return " or ".join(parts)


class _DirectionState:
    __slots__ = ("deque", "bytes_throttled", "bytes_dropped", "bytes_sent")

    def __init__(self):
        self.deque = collections.deque()
        self.bytes_throttled = 0
        self.bytes_dropped = 0
        self.bytes_sent = 0


class FlowShaper:
    """把指定端点的流量限制到 rate_bps 字节/秒（上下行独立计算）。"""

    def __init__(self, dll_path, rate_bps, log=None):
        self._dll_path = dll_path
        self.rate_bps = max(float(rate_bps), 64.0)
        # 用户态队列上限：至少 64KB，约 15 秒的量
        self.queue_cap = max(65536, int(self.rate_bps * 15))
        self._log = log or (lambda msg: None)

        self._wd = None
        self._stopping = threading.Event()
        self._recv_thread = None
        self._pump_thread = None
        self._lock = threading.Lock()
        self._out = _DirectionState()
        self._in = _DirectionState()
        self._max_pkt = 1500  # 观测到的最大包长（回环/LSO 网卡可达 64KB）
        self._tokens = 0.0    # 上下行共享的令牌池
        self._last_capture = None  # 最近一次捕获到包的时刻
        self._started_at = None
        self._filter = ""

    # ------------------------------------------------------------------
    @property
    def running(self):
        return self._wd is not None

    @property
    def filter(self):
        return self._filter

    def start(self, tcp_flows, udp_ports, tcp_flows6=None, filter_override=None):
        if self._wd is not None:
            self.stop()
        filter_str = filter_override or build_filter(tcp_flows, udp_ports,
                                                     tcp_flows6)
        if not filter_str:
            raise ValueError("没有可用的端点，无法限速")

        wd = windivert.WinDivert(self._dll_path)
        wd.open(filter_str, priority=0, flags=0)
        # 内核侧队列保持默认量级：接收线程一旦卡住，积压 2 秒就放行/丢弃，
        # 让 TCP 快速重传恢复，避免长时间黑洞
        wd.set_param(windivert.PARAM_QUEUE_TIME, 2000)

        self._wd = wd
        self._filter = filter_str
        self._stopping.clear()
        self._out, self._in = _DirectionState(), _DirectionState()
        self._started_at = time.monotonic()

        self._recv_thread = threading.Thread(target=self._recv_loop,
                                             name="wd-recv", daemon=True)
        self._pump_thread = threading.Thread(target=self._pump_loop,
                                             name="wd-pump", daemon=True)
        self._recv_thread.start()
        self._pump_thread.start()
        self._log("限速已开启 @ %d B/s(仅下载方向) 端点: TCP=%s UDP=%s"
                  % (self.rate_bps,
                     sorted(tcp_flows | set(tcp_flows6 or ())),
                     sorted(udp_ports)))

    def stop(self, flush=True, flush_rate=262144.0):
        """停止限速。flush=True 时把排队的包以 flush_rate 字节/秒注回，
        避免瞬时大突发；flush=False 直接丢弃队列。"""
        wd = self._wd
        if wd is None:
            return
        self._stopping.set()
        # 唤醒阻塞在 recv 的线程（recv 侧关闭后 send 侧仍可用）
        try:
            wd.shutdown(windivert.SHUTDOWN_RECV)
        except Exception:
            pass
        if self._recv_thread:
            self._recv_thread.join(timeout=2.0)
        if self._pump_thread:
            self._pump_thread.join(timeout=2.0)

        total = 0
        for st in (self._out, self._in):
            with self._lock:
                total += sum(len(p) for p, _ in st.deque)
        if total:
            self._log("停止限速，排队数据 %d 字节 (flush=%s)" % (total, flush))
        if flush and total:
            budget = 0.0
            last = time.monotonic()
            remaining = total
            deadline = time.monotonic() + 10.0
            while remaining > 0 and time.monotonic() < deadline:
                now = time.monotonic()
                budget += flush_rate * (now - last)
                last = now
                sent = self._drain_one(budget)
                if sent:
                    budget -= sent
                    remaining -= sent
                else:
                    time.sleep(0.004)
        for st in (self._out, self._in):
            with self._lock:
                st.deque.clear()
        try:
            wd.close()
        except Exception:
            pass
        self._wd = None

    # ------------------------------------------------------------------
    def _recv_loop(self):
        buf = _recv_buffer()
        wd = self._wd
        t0 = time.monotonic()
        lag_hinted = False
        while not self._stopping.is_set():
            try:
                packet, addr = wd.recv(buf)
            except windivert.WinDivertError as exc:
                if not self._stopping.is_set():
                    self._log("限速接收线程退出: %r" % exc, "warn")
                break
            except Exception as exc:
                if not self._stopping.is_set():
                    self._log("限速接收线程异常: %r" % exc, "error")
                break
            if self._stopping.is_set():
                break
            self._last_capture = time.monotonic()
            if not lag_hinted and time.monotonic() - t0 > 1.0:
                self._log("注意：首个包在开限速后 %.1f 秒才被捕获" % (time.monotonic() - t0),
                          "warn")
                lag_hinted = True
            if self._stopping.is_set():
                break
            st = self._out if addr.outbound else self._in
            with self._lock:
                if len(packet) > self._max_pkt:
                    self._max_pkt = len(packet)
                if len(st.deque) * 1500 >= self.queue_cap:
                    st.bytes_dropped += len(packet)
                    continue
                st.deque.append((packet, addr))
                st.bytes_throttled += len(packet)

    def _pump_loop(self):
        """令牌桶放行：上行+下行共用一个桶，合计 rate_bps（对齐
        NetLimiter 等工具的"按进程限速"语义）。两个方向交替出队，
        防止单方向大流量把对方饿死。
        桶容量必须 >= 最大包长，否则大包永远凑不齐 token 会饿死。"""
        last = time.monotonic()
        while not self._stopping.is_set():
            time.sleep(0.002)
            now = time.monotonic()
            dt, last = now - last, now
            batch = []
            with self._lock:
                burst_cap = max(self.rate_bps * 0.25, self._max_pkt)
                self._tokens = min(burst_cap, self._tokens + self.rate_bps * dt)
                progressed = True
                turn = 0
                while progressed and not self._stopping.is_set():
                    progressed = False
                    dirs = ((self._out, self._in) if turn == 0
                            else (self._in, self._out))
                    for st in dirs:
                        if not st.deque:
                            continue
                        size = len(st.deque[0][0])
                        if size > self._tokens:
                            continue
                        self._tokens -= size
                        batch.append((st, st.deque.popleft()))
                        turn ^= 1
                        progressed = True
                        break
            for st, (packet, addr) in batch:
                try:
                    self._wd.send(packet, addr)
                    st.bytes_sent += len(packet)
                except Exception:
                    # handle 正在关闭等场景：包丢弃，TCP 重传兜底
                    st.bytes_dropped += len(packet)

    def _drain_one(self, budget):
        """stop(flush=True) 用：在 budget 字节额度内发一个排队包，返回发送字节数。"""
        with self._lock:
            for st in (self._out, self._in):
                if st.deque and len(st.deque[0][0]) <= budget:
                    packet, addr = st.deque.popleft()
                    break
            else:
                return 0
        wd = self._wd
        if wd is None:
            return 0
        try:
            wd.send(packet, addr)
            return len(packet)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    def stats(self):
        with self._lock:
            since_cap = None
            if self._last_capture is not None:
                since_cap = time.monotonic() - self._last_capture
            return {
                "running": self._wd is not None,
                "recv_alive": (self._recv_thread is not None
                               and self._recv_thread.is_alive()),
                "since_capture": since_cap,
                "elapsed": (time.monotonic() - self._started_at
                            if self._started_at else 0.0),
                "out_throttled": self._out.bytes_throttled,
                "in_throttled": self._in.bytes_throttled,
                "out_sent": self._out.bytes_sent,
                "in_sent": self._in.bytes_sent,
                "dropped": self._out.bytes_dropped + self._in.bytes_dropped,
                "queued": len(self._out.deque) + len(self._in.deque),
            }


class ThrottleSession:
    """带自动换挡的限速会话：FlowShaper 的薄封装，
    负责端点变化时的平滑重启（短暂丢包，TCP 自动重传）。"""

    def __init__(self, dll_path, rate_bps, log=None):
        self._dll_path = dll_path
        self._rate_bps = rate_bps
        self._log = log or (lambda msg: None)
        self._shaper = None

    def update(self, tcp4, udp4, tcp6=None, udp6=None, force=False):
        """确保限速覆盖给定端点集合；集合变化时平滑重启。
        force=True 时无视过滤串相同与否强制重建句柄（用于捕获异常的自愈）。
        udp4/udp6 是本地端口集合（UDP 过滤按端口，天然覆盖 v4+v6）。"""
        udp_all = set(udp4 or ()) | set(udp6 or ())
        flt = build_filter(tcp4, udp_all, tcp6)
        if (self._shaper is not None and self._shaper.filter == flt
                and not force):
            return
        if self._shaper is not None:
            self._shaper.stop(flush=True)
            self._shaper = None
        if not tcp4 and not udp_all and not tcp6:
            self._log("警告：游戏进程当前没有任何网络连接，等待下一轮扫描")
            return
        self._shaper = FlowShaper(self._dll_path, self._rate_bps, self._log)
        self._shaper.start(tcp4, udp_all, tcp6)

    def release(self):
        if self._shaper is not None:
            self._shaper.stop(flush=True)
            self._shaper = None

    @property
    def active(self):
        return self._shaper is not None and self._shaper.running

    def stats(self):
        if self._shaper is None:
            return {"running": False}
        return self._shaper.stats()
