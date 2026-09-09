# -*- coding: utf-8 -*-
"""游戏进程发现 + 网络端点扫描。

进程识别：按进程名关键字匹配（配置 keywords，如 ["yan", "winds"]），
并补充窗口标题匹配（如 "燕云"、"Where Winds Meet"）。
端点扫描：TCP 取 ESTABLISHED 连接的远端端点，UDP 取本地端口。
"""
import ctypes
import socket
from ctypes import wintypes

import psutil

user32 = ctypes.WinDLL("user32", use_last_error=True)
_enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def _windows_of(pid):
    """枚举属于 pid 的可见顶层窗口句柄。"""
    results = []

    def cb(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                results.append((hwnd, buf.value))
        return True

    user32.EnumWindows(_enum_proc(cb), 0)
    return results


def find_processes(keywords):
    """按进程名/窗口标题关键字找候选进程，返回 [(pid, name, title, exe)]。
    title/exe 可能为空。按 pid 升序。"""
    kw = [k.strip().lower() for k in keywords if k and k.strip()]
    if not kw:
        return []
    hits = {}
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (p.info["name"] or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        matched = any(k in name for k in kw)
        titles = []
        if not matched:
            titles = _windows_of(p.info["pid"])
            matched = any(any(k in t.lower() for k in kw) for _, t in titles)
        if matched:
            title = titles[0][1] if titles else (
                _windows_of(p.info["pid"])[0][1]
                if _windows_of(p.info["pid"]) else "")
            hits[p.info["pid"]] = (p.info["pid"], p.info["name"] or "?",
                                   title, p.info["exe"] or "")
    return [hits[pid] for pid in sorted(hits)]


def scan_flows(pid):
    """扫描进程网络端点。
    返回 (tcp_v4 {(ip,port)}, udp_v4 {port}, tcp_v6 {(ip,port)}, udp_v6 {port})。
    psutil 拿不到时返回空集合。"""
    tcp4, udp4, tcp6, udp6 = set(), set(), set(), set()
    try:
        conns = psutil.Process(pid).net_connections(kind="inet")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return tcp4, udp4, tcp6, udp6
    for c in conns:
        try:
            if c.type == socket.SOCK_STREAM:
                if not c.raddr:
                    continue
                if c.status == psutil.CONN_ESTABLISHED:
                    if c.family == socket.AF_INET:
                        tcp4.add((c.raddr.ip, c.raddr.port))
                    elif c.family == socket.AF_INET6:
                        tcp6.add((c.raddr.ip, c.raddr.port))
            elif c.type == socket.SOCK_DGRAM:
                if not c.laddr:
                    continue
                if c.family == socket.AF_INET:
                    udp4.add(c.laddr.port)
                elif c.family == socket.AF_INET6:
                    udp6.add(c.laddr.port)
        except Exception:
            continue
    return tcp4, udp4, tcp6, udp6


def describe_flows(tcp4, udp4, tcp6, udp6):
    parts = []
    if tcp4:
        parts.append("TCP %s" % sorted(tcp4))
    if tcp6:
        parts.append("TCPv6 %d条" % len(tcp6))
    if udp4:
        parts.append("UDP本地端口 %s" % sorted(udp4))
    if udp6:
        parts.append("UDPv6本地端口 %s" % sorted(udp6))
    return "；".join(parts) if parts else "（无连接）"
