# -*- coding: utf-8 -*-
"""WinDivert 2.2 轻量 ctypes 封装（只封装 NETWORK 层需要的部分）。

结构体布局严格对照官方 include/windivert.h (v2.2.2)：
    WINDIVERT_ADDRESS = INT64 Timestamp
                      + UINT32 位域(Layer:8 Event:8 Sniffed:1 Outbound:1 Loopback:1
                                    Impostor:1 IPv6:1 IPChecksum:1 TCPChecksum:1 UDPChecksum:1
                                    Reserved1:8)
                      + UINT32 Reserved2
                      + 64 字节 union 数据
    共 80 字节。

线程模型：允许一个线程 recv、另一个线程 send（官方支持）。
停止顺序：WinDivertShutdown(RECV) 唤醒阻塞的 recv -> 排空队列后 Close。
"""
import ctypes
import os
import re
import subprocess
import time

LAYER_NETWORK = 0

# WinDivertOpen flags
FLAG_SNIFF = 0x0001
FLAG_DROP = 0x0002
FLAG_RECV_ONLY = 0x0004
FLAG_SEND_ONLY = 0x0008
FLAG_NO_INSTALL = 0x0010
FLAG_FRAGMENTS = 0x0020

# WinDivertSetParam
PARAM_QUEUE_LENGTH = 0
PARAM_QUEUE_TIME = 1
PARAM_QUEUE_SIZE = 2

# WinDivertShutdown
SHUTDOWN_RECV = 0x1
SHUTDOWN_SEND = 0x2
SHUTDOWN_BOTH = 0x3

MTU_MAX = 40 + 0xFFFF  # 65575，官方 WINDIVERT_MTU_MAX

QUEUE_LENGTH_MAX = 16384
QUEUE_TIME_MAX = 16000        # ms
QUEUE_SIZE_MAX = 33554432     # 32MB

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_OPEN_ERROR_HINTS = {
    2: "找不到 WinDivert64.sys（.sys 必须和 .dll 在同一目录）",
    3: "驱动路径无效",
    5: "拒绝访问：请以管理员身份运行；也可能被杀软/反作弊拦截",
    87: "过滤串语法错误: ",
    577: "驱动被 Windows 拒绝（驱动黑名单 / 内存完整性 HVCI）。"
         "可在『Windows 安全中心-设备安全性-内核隔离』中关闭内存完整性后重试",
    1058: "WinDivert 驱动服务被禁用",
}


class WinDivertError(OSError):
    """WinDivert 调用失败。"""


def cleanup_stale_services(names=("WinDivert", "tjnet")):
    """删除指向已失效路径的 WinDivert 驱动服务。

    WinDivert 首次运行会把当时解包目录里的 .sys 注册成系统服务，而
    onefile 打包的解包目录每次启动都会变；旧服务留着会让之后的运行
    报 WinError 2。这里检查服务指向的文件是否还存在，不存在就删除
    服务，让本次的 WinDivert.dll 用当前路径重新安装。
    （需要管理员权限；任何失败都静默忽略，不影响正常流程。）
    """
    for name in names:
        try:
            # sc.exe 输出是系统 OEM 编码（中文系统为 GBK），按 UTF-8 解码会失败
            qc = subprocess.run(["sc.exe", "qc", name],
                                capture_output=True,
                                encoding="gbk", errors="replace", timeout=10)
            m = re.search(r"BINARY_PATH_NAME\s*:\s*(.+)", qc.stdout or "")
            if not m:
                continue  # 服务未安装
            raw = m.group(1).strip().strip('"')
            path = raw.replace("\\??\\", "")
            if os.path.isfile(path):
                continue  # 指向的驱动文件还在，服务有效
            subprocess.run(["sc.exe", "stop", name],
                           capture_output=True, timeout=10)
            time.sleep(0.3)
            subprocess.run(["sc.exe", "delete", name],
                           capture_output=True, timeout=10)
        except Exception:
            continue


class WINDIVERT_ADDRESS(ctypes.Structure):
    _fields_ = [
        ("Timestamp", ctypes.c_int64),
        ("_word1", ctypes.c_uint32),
        ("Reserved2", ctypes.c_uint32),
        ("Data", ctypes.c_ubyte * 64),
    ]

    @property
    def layer(self):
        return self._word1 & 0xFF

    @property
    def outbound(self):
        return bool((self._word1 >> 17) & 1)

    @property
    def loopback(self):
        return bool((self._word1 >> 18) & 1)

    @property
    def ipv6(self):
        return bool((self._word1 >> 20) & 1)


class WinDivert:
    """单个 NETWORK 层 handle 的封装，线程安全（recv/send 可并发）。"""

    def __init__(self, dll_path):
        dll_path = os.path.abspath(dll_path)
        if not os.path.isfile(dll_path):
            raise WinDivertError("找不到 %s，请确认 vendored 目录完整" % dll_path)
        try:
            os.add_dll_directory(os.path.dirname(dll_path))
        except (AttributeError, OSError):
            pass
        self._dll = ctypes.CDLL(dll_path, use_last_error=True)
        d = self._dll

        d.WinDivertOpen.argtypes = [ctypes.c_char_p, ctypes.c_int,
                                    ctypes.c_int16, ctypes.c_uint64]
        d.WinDivertOpen.restype = ctypes.c_void_p

        d.WinDivertRecv.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
                                    ctypes.POINTER(WINDIVERT_ADDRESS)]
        d.WinDivertRecv.restype = ctypes.c_bool

        d.WinDivertSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
                                    ctypes.POINTER(WINDIVERT_ADDRESS)]
        d.WinDivertSend.restype = ctypes.c_bool

        d.WinDivertShutdown.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        d.WinDivertShutdown.restype = ctypes.c_bool

        d.WinDivertClose.argtypes = [ctypes.c_void_p]
        d.WinDivertClose.restype = ctypes.c_bool

        d.WinDivertSetParam.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64]
        d.WinDivertSetParam.restype = ctypes.c_bool

        d.WinDivertHelperCalcChecksums.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                                   ctypes.POINTER(WINDIVERT_ADDRESS),
                                                   ctypes.c_uint64]
        d.WinDivertHelperCalcChecksums.restype = ctypes.c_bool

        self._handle = None

    # ------------------------------------------------------------------
    def open(self, filter_str, priority=0, flags=0):
        """打开 NETWORK 层 handle。失败抛 WinDivertError，附中文诊断。"""
        # 先清掉指向已失效路径的残留驱动服务（如旧版 _MEI 目录被清理）
        cleanup_stale_services()
        h = self._dll.WinDivertOpen(filter_str.encode("utf-8"),
                                    LAYER_NETWORK, priority, flags)
        if h in (None, INVALID_HANDLE_VALUE) or not h:
            err = ctypes.get_last_error()
            hint = _OPEN_ERROR_HINTS.get(err, "")
            if err == 87:
                hint = hint + filter_str
            raise WinDivertError(
                "WinDivertOpen 失败 (WinError %d)。%s" % (err, hint))
        self._handle = ctypes.c_void_p(h)
        return self._handle

    def set_param(self, param, value):
        if not self._dll.WinDivertSetParam(self._handle, param, value):
            raise WinDivertError("WinDivertSetParam 失败 (WinError %d)"
                                 % ctypes.get_last_error())

    def recv(self, buffer):
        """从内核取一个包。buffer 需为 c_ubyte 数组（MTU_MAX）。
        返回 (packet_bytes, addr)。"""
        recv_len = ctypes.c_uint(0)
        addr = WINDIVERT_ADDRESS()
        if not self._dll.WinDivertRecv(self._handle, buffer, len(buffer),
                                       ctypes.byref(recv_len), ctypes.byref(addr)):
            raise WinDivertError("WinDivertRecv 失败 (WinError %d)"
                                 % ctypes.get_last_error())
        return bytes(buffer[:recv_len.value]), addr

    def send(self, packet, addr):
        """把包注回协议栈（addr 用 recv 时返回的原地址即可）。"""
        sent = ctypes.c_uint(0)
        if not self._dll.WinDivertSend(self._handle, packet, len(packet),
                                       ctypes.byref(sent), ctypes.byref(addr)):
            raise WinDivertError("WinDivertSend 失败 (WinError %d)"
                                 % ctypes.get_last_error())

    def shutdown(self, how=SHUTDOWN_RECV):
        if self._handle is not None:
            self._dll.WinDivertShutdown(self._handle, how)

    def close(self):
        if self._handle is not None:
            self._dll.WinDivertClose(self._handle)
            self._handle = None

    @property
    def handle(self):
        return self._handle
