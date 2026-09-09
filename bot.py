# -*- coding: utf-8 -*-
"""炸鱼循环调度：限速 → 疯狂放太极 → 解限恢复 → 循环。

一个循环：
  [限速期]  开启限速(端点自动扫描)，每 cast_interval 秒按一次技能键，
            共持续 throttle_seconds；
  [恢复期]  关闭限速并回灌排队包，让游戏恢复正常同步，持续 release_seconds，
            鱼获自动进背包无需拾取；
  重复，直到达到 cycles 次数或手动停止。

安全设计：
  - 开始后自动把游戏窗口置前（前台按键模式依赖）；
  - 每轮限速期都会重新扫描端点（游戏断线重连后端点会变）；
  - 游戏进程消失 / 无网络连接时自动暂停等待而不是空转限速；
  - F9 暂停/继续，F10 停止，F12 紧急解限并停止（GUI 与命令行均注册全局热键）。
"""
import random
import threading
import time

import gameinput
import gameproc


class FishBot(threading.Thread):
    IDLE = "待机"
    THROTTLE = "限速炸鱼中"
    RELEASE = "解限恢复中"
    WAITING = "等待游戏连接"
    PAUSED = "已暂停"
    STOPPED = "已停止"
    ERROR = "出错"

    # 游戏进程识别关键字（燕云十六声客户端进程名含 yysls）
    PROCESS_KEYWORDS = ["yysls"]

    # 太极是点按技能：固定的按键按下时长（秒），实现细节不暴露到界面
    TAP_HOLD_SECONDS = 0.045

    def __init__(self, cfg, log=None, on_state=None):
        super().__init__(name="fish-bot", daemon=True)
        self.cfg = dict(cfg)
        self._log = log or (lambda msg, level="info": None)
        self._on_state = on_state or (lambda **kw: None)
        self._stop_evt = threading.Event()
        self._pause_evt = threading.Event()   # set = 正常运行；clear = 暂停
        self._pause_evt.set()
        self._emergency = threading.Event()
        self._state = self.IDLE
        self._cycle = 0
        self._casts = 0

    # ---------------- 对外控制 ----------------
    def stop(self, emergency=False):
        if emergency:
            self._emergency.set()
        self._pause_evt.set()
        self._stop_evt.set()

    def toggle_pause(self):
        if self._stop_evt.is_set():
            return
        if self._pause_evt.is_set():
            self._pause_evt.clear()
            self._set_state(self.PAUSED)
            self._log("已暂停（F9 继续 / F12 紧急解限停止）", "warn")
        else:
            self._pause_evt.set()
            self._log("继续运行")

    @property
    def state(self):
        return self._state

    @property
    def cycle(self):
        return self._cycle

    @property
    def casts(self):
        return self._casts

    # ---------------- 内部工具 ----------------
    def _set_state(self, state, **extra):
        self._state = state
        try:
            self._on_state(state=state, cycle=self._cycle, casts=self._casts,
                           **extra)
        except Exception:
            pass

    def _sleep(self, seconds):
        """分片睡眠，期间响应停止/暂停。返回 False 表示应中止。"""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stop_evt.is_set():
                return False
            if not self._emergency.is_set():
                self._pause_evt.wait(timeout=0.2)
            time.sleep(0.05)
        return not self._stop_evt.is_set()

    def _cfg_get(self, key, default):
        return self.cfg.get(key, default)

    def _pick_process(self):
        keywords = self._cfg_get("process_keywords", None) or self.PROCESS_KEYWORDS
        cands = gameproc.find_processes(keywords)
        if not cands:
            return None
        # 优先选有活动连接的那个（游戏本体而不是启动器）
        best, best_score = None, -1
        for pid, name, title, exe in cands:
            tcp4, udp4, tcp6, udp6 = gameproc.scan_flows(pid)
            score = len(tcp4) + len(udp4) + len(tcp6) + len(udp6)
            if score > best_score:
                best, best_score = (pid, name, title), score
        return best

    # ---------------- 主循环 ----------------
    def run(self):
        import os
        import paths
        import throttler
        dll = self._cfg_get("windivert_dll", paths.WINDIVERT_DLL)
        if not os.path.isfile(dll):
            # 兜底：旧配置里可能存有过期的一次性解包路径
            dll = paths.WINDIVERT_DLL
        session = throttler.ThrottleSession(dll,
                                            self._cfg_get("rate_bps", 1024.0),
                                            log=self._log)
        try:
            self._loop(session)
        except Exception as exc:
            self._set_state(self.ERROR)
            self._log("机器人异常退出: %r" % exc, "error")
        finally:
            try:
                session.release()
            except Exception:
                pass
            self._set_state(self.STOPPED)
            self._log("机器人已停止，网络已恢复正常")

    def _loop(self, session):
        throttle_s = float(self._cfg_get("throttle_seconds", 600))
        release_s = float(self._cfg_get("release_seconds", 10))
        cast_interval = float(self._cfg_get("cast_interval", 1.4))
        cast_key = self._cfg_get("cast_key", "r")
        hold_ms = int(self.TAP_HOLD_SECONDS * 1000)
        cycles = int(self._cfg_get("cycles", 0))
        jitter = float(self._cfg_get("jitter", 0.15))
        input_mode = self._cfg_get("input_mode", "foreground")
        refresh = float(self._cfg_get("flow_refresh_seconds", 5))
        scancode = bool(self._cfg_get("send_scancode", False))
        pm_char = bool(self._cfg_get("pm_wm_char", False))
        stop_after = float(self._cfg_get("stop_after_minutes", 0)) * 60.0
        t_start = time.monotonic()

        def time_up():
            """定时停止：到点触发正常停止（立即解限）。"""
            if stop_after and time.monotonic() - t_start >= stop_after:
                self._log("定时 %.4g 分钟已到，自动停止" % (stop_after / 60.0),
                          "warn")
                self._stop_evt.set()
                return True
            return False

        def press(key):
            if input_mode == "postmessage" and hwnd:
                gameinput.send_key_postmessage(hwnd, key, hold_ms,
                                               with_char=pm_char)
            else:
                gameinput.send_key_foreground(key, hold_ms, jitter,
                                              scancode=scancode)

        self._log("启动：限速 %.1fKB/s × %ds → 解限 %ds，技能键 %r 每 %.1fs 一次"
                  % (self._cfg_get("rate_bps", 1024.0) / 1024.0,
                     throttle_s, release_s, cast_key, cast_interval))

        while not self._stop_evt.is_set() and not self._emergency.is_set():
            if cycles and self._cycle >= cycles:
                self._log("已完成 %d 轮，正常收工" % cycles)
                return
            if time_up():
                return

            proc = self._pick_process()
            if proc is None:
                self._set_state(self.WAITING)
                self._log("没找到游戏进程（关键字 %s），3 秒后重试..."
                          % self._cfg_get("process_keywords", []), "warn")
                if not self._sleep(3.0):
                    return
                continue

            pid, name, title = proc
            if input_mode == "foreground":
                if gameinput.activate_window(pid):
                    self._log("已把游戏窗口带到前台，请保持游戏在前台（前台按键模式依赖）")
                else:
                    self._log("没能把游戏窗口置前；前台模式要求游戏窗口在前台", "warn")
            hwnd = gameinput.find_window_by_pid(pid) if input_mode == "postmessage" else 0
            if input_mode == "postmessage" and not hwnd:
                self._log("找不到 %s 的窗口，postmessage 模式不可用，改用前台模式" % name,
                          "warn")
                input_mode = "foreground"

            # ---------- 限速炸鱼阶段 ----------
            self._set_state(self.THROTTLE, pid=pid, name=name)
            self._log("第 %d 轮：目标 %s (pid %d)" % (self._cycle + 1, name, pid))
            tcp4, udp4, tcp6, udp6 = gameproc.scan_flows(pid)
            if not (tcp4 or udp4 or tcp6 or udp6):
                self._log("游戏进程没有活动网络连接，本轮跳过限速直接等待", "warn")
                if not self._sleep(3.0):
                    return
                continue
            try:
                session.update(tcp4, udp4, tcp6, udp6)
            except Exception as exc:
                self._log("开启限速失败: %r" % exc, "error")
                self._set_state(self.ERROR)
                return
            if not session.active:
                if not self._sleep(2.0):
                    return
                continue

            phase_end = time.monotonic() + throttle_s
            next_scan = 0.0
            next_cast = 0.0
            next_stats = 0.0
            capture_check_at = time.monotonic() + 3.0
            while True:
                if self._stop_evt.is_set() or self._emergency.is_set():
                    session.release()
                    return
                if time_up():
                    session.release()
                    return
                now = time.monotonic()
                if now >= phase_end:
                    break
                self._pause_evt.wait(timeout=0.1)
                if self._stop_evt.is_set():
                    session.release()
                    return
                now = time.monotonic()
                if now >= next_stats:
                    next_stats = now + 10.0
                    st = session.stats()
                    if st.get("running"):
                        self._log("限速统计: 捕获 出%.1fKB/入%.1fKB，已放行 "
                                  "出%.1fKB/入%.1fKB，队列%d 丢弃%d"
                                  % (st["out_throttled"] / 1024.0,
                                     st["in_throttled"] / 1024.0,
                                     st["out_sent"] / 1024.0,
                                     st["in_sent"] / 1024.0,
                                     st["queued"], st["dropped"]))
                if now >= capture_check_at and session.active:
                    # 自愈（保守判据）：接收线程死亡立即重建；持续 10 秒完全
                    # 没有任何下行包才重建（挂机时下行稀疏是正常的，勿误报）
                    st = session.stats()
                    dead = not st.get("recv_alive", True)
                    silent = (st.get("since_capture") or 0) > 10.0
                    if dead or silent:
                        if dead:
                            self._log("限速接收线程死亡，重建句柄", "warn")
                        else:
                            self._log("已 %.0f 秒没有任何下行包，重建句柄重试"
                                      % st["since_capture"], "warn")
                        t4, u4, t6, u6 = gameproc.scan_flows(pid)
                        if t4 or u4 or t6 or u6:
                            session.update(t4, u4, t6, u6, force=True)
                            capture_check_at = time.monotonic() + 3.0
                if now >= next_scan:
                    next_scan = now + refresh
                    t4, u4, t6, u6 = gameproc.scan_flows(pid)
                    if t4 or u4 or t6 or u6:
                        try:
                            session.update(t4, u4, t6, u6)
                        except Exception as exc:
                            self._log("端点刷新失败: %r" % exc, "error")
                if now >= next_cast:
                    next_cast = now + cast_interval * (1.0 + random.uniform(
                        -jitter, jitter))
                    try:
                        press(cast_key)
                        self._casts += 1
                    except gameinput.KeyInputError as exc:
                        self._log(str(exc), "error")
                        session.release()
                        self._set_state(self.ERROR)
                        return
            self._set_state(self.THROTTLE, casts=self._casts)
            st = session.stats()

            # ---------- 解限恢复阶段 ----------
            session.release()
            if (st.get("running")
                    and st.get("out_throttled", 0) + st.get("in_throttled", 0) == 0):
                self._log("警告：整个限速期捕获到的游戏流量为 0(%r)，说明限速没有"
                          "作用到游戏服务器的连接（可能走了加速器/代理，或匹配到"
                          "了别的进程）。可尝试关闭加速器后重试" % st, "warn")
            self._set_state(self.RELEASE)
            self._log("解限 %ds，游戏恢复正常同步，鱼获自动进背包" % release_s)
            if not self._sleep(release_s):
                return

            self._cycle += 1
            self._set_state(self.IDLE, cycle=self._cycle, casts=self._casts)
            self._log("第 %d 轮完成，累计施放 %d 次" % (self._cycle, self._casts))
