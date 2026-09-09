# -*- coding: utf-8 -*-
"""向游戏发送按键。两种模式：

foreground  —— SendInput 注入系统输入流，游戏窗口必须在前台。
               用扫描码发送，兼容 DirectInput/RawInput 类游戏引擎。
postmessage —— PostMessage 直接向窗口投递 WM_KEYDOWN/WM_KEYUP，
               理论上后台可用，但很多游戏引擎只读硬件输入，未必生效；
               属于实验模式，不生效就用回 foreground。
"""
import ctypes
import random
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

_enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

MAPVK_VK_TO_VSC = 0

NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "tab": 0x09, "shift": 0x10, "lshift": 0xA0, "rshift": 0xA1,
    "ctrl": 0x11, "lctrl": 0xA2, "rctrl": 0xA3, "alt": 0x12, "lalt": 0xA4,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "scrolllock": 0x91, "numlock": 0x90, "pause": 0x13,
    "mouse1": None, "mouse2": None,  # 占位：不支持鼠标，避免误配
}
for _i in range(1, 13):
    NAMED_KEYS["f%d" % _i] = 0x6F + _i

EXTENDED_VKS = {0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x21, 0x22, 0x23, 0x24}


class KeyInputError(RuntimeError):
    pass


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


def resolve_key(key):
    """'r' / 'f1' / 'space' -> (vk, scancode)。"""
    k = (key or "").strip().lower()
    if not k:
        raise KeyInputError("按键名为空")
    if len(k) == 1:
        if k.isdigit():
            vk = 0x30 + int(k)
        elif k.isalpha():
            vk = ord(k.upper())
        else:
            vk = wintypes.WORD(user32.VkKeyScanW(ord(k)) & 0xFF).value
    elif k in NAMED_KEYS:
        vk = NAMED_KEYS[k]
        if vk is None:
            raise KeyInputError("暂不支持 %s，请配置键盘按键" % k)
    else:
        raise KeyInputError("无法识别按键名: %r" % key)
    sc = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    return vk, sc


def send_key_foreground(key, hold_ms=45, jitter=0.0, scancode=False):
    """前台模式：SendInput。默认发虚拟键（VK 路径，系统自动补扫描码，
    绝大多数程序都能收到）；个别引擎只认扫描码时把 scancode=True。
    要求游戏窗口处于前台。"""
    vk, sc = resolve_key(key)
    flags_down = KEYEVENTF_SCANCODE if scancode else 0
    flags_up = KEYEVENTF_KEYUP | (KEYEVENTF_SCANCODE if scancode else 0)
    if vk in EXTENDED_VKS:
        flags_down |= KEYEVENTF_EXTENDEDKEY
        flags_up |= KEYEVENTF_EXTENDEDKEY

    def _inject(flags, vkey, scan):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki = KEYBDINPUT(vkey, scan, flags, 0, 0)
        sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent != 1:
            raise KeyInputError(
                "SendInput 被拒绝 (WinError %d)：前台窗口可能收到了 UIPI 保护"
                % ctypes.get_last_error())

    _inject(flags_down, vk, sc)
    hold = hold_ms / 1000.0
    if jitter > 0:
        hold *= 1.0 + random.uniform(-jitter, jitter)
    time.sleep(max(hold, 0.01))
    _inject(flags_up, vk, sc)


def send_key_postmessage(hwnd, key, hold_ms=45, with_char=False):
    """后台模式：向指定窗口句柄投递 WM_KEYDOWN/WM_KEYUP。
    with_char=True 时补发 WM_CHAR（给只认字符消息的老式控件）；
    多数程序自己翻译 WM_KEYDOWN，补发会重复输入，默认关闭。
    游戏可能忽略本模式的消息，实验性质。"""
    vk, sc = resolve_key(key)
    lp_down = 1 | (sc << 16)
    lp_up = lp_down | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lp_down)
    if with_char and (len(key) == 1 or key.lower() == "space"):
        ch = " " if key.lower() == "space" else key
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), lp_down)
    time.sleep(max(hold_ms / 1000.0, 0.01))
    user32.PostMessageW(hwnd, WM_KEYUP, vk, lp_up)


def find_window_by_pid(pid):
    """找进程的第一个可见主窗口，找不到返回 0。"""
    hwnds = []

    def cb(h, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(h):
            hwnds.append(h)
        return True

    user32.EnumWindows(_enum_proc(cb), 0)
    return hwnds[0] if hwnds else 0


def activate_window(pid):
    """把 pid 的窗口带到前台（点开始后自动聚焦游戏用）。
    ALT 技巧绕过前台锁；窗口最小化时先还原。成功返回 True。"""
    hwnd = find_window_by_pid(pid)
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.2)
    user32.keybd_event(0x12, 0, 0, 0)   # ALT down，解锁 SetForegroundWindow
    time.sleep(0.05)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 2, 0)   # ALT up
    time.sleep(0.1)
    return user32.GetForegroundWindow() == hwnd
