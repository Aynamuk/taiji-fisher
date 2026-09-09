# -*- coding: utf-8 -*-
"""太极炸鱼助手 - CustomTkinter 深色界面。

约定：每次改动 GUI 后运行 python tests/grab_gui.py 重新生成 docs/gui_preview.png。
托盘：开始任务后自动缩进托盘（后台模式不置前游戏，前台模式由 bot 置前游戏），
托盘左键恢复窗口，右键菜单可显示/停止/退出；任务结束自动恢复窗口。
"""
import json
import queue
import time

import customtkinter as ctk

import gameproc
import paths
from bot import FishBot

CONFIG_PATH = paths.CONFIG_PATH

# 游戏进程识别关键字（燕云十六声客户端进程名含 yysls）
PROCESS_KEYWORDS = ["yysls"]

# 输入模式：内部值 -> 界面显示名
MODE_DISPLAY = {
    "foreground": "前台模式（推荐）",
    "postmessage": "后台模式（兼容性差）",
}
MODE_INTERNAL = {v: k for k, v in MODE_DISPLAY.items()}

DEFAULT_CFG = {
    "rate_bps": 512.0,  # 0.5KB/s，实测可用值；判定标准：日志队列 > 0
    "throttle_seconds": 600,
    "release_seconds": 10,
    "cast_key": "r",
    "cast_interval": 1.4,
    "cycles": 0,
    "stop_after_minutes": 0,
    "jitter": 0.15,
    "input_mode": "foreground",
    "flow_refresh_seconds": 5,
    "windivert_dll": paths.WINDIVERT_DLL,
}

# 阶段 -> (显示色, 说明)
STATE_STYLE = {
    FishBot.IDLE: ("#9aa3ad", "待机"),
    FishBot.THROTTLE: ("#ff7a66", "限速炸鱼中"),
    FishBot.RELEASE: ("#4dd882", "解限恢复中"),
    FishBot.WAITING: ("#f0c04a", "等待游戏连接"),
    FishBot.PAUSED: ("#5aa7ff", "已暂停"),
    FishBot.STOPPED: ("#9aa3ad", "已停止"),
    FishBot.ERROR: ("#ff4d4d", "出错"),
}

CARD = "#242429"
BG = "#1b1b1f"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("太极炸鱼助手 · 燕云十六声")
        self.geometry("780x640")
        self.minsize(720, 600)
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")

        self.cfg = dict(DEFAULT_CFG)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self.cfg.update(json.load(f))
        except Exception:
            pass
        # 旧配置可能存有过期的一次性解包路径，强制用本次运行的真实路径
        self.cfg["windivert_dll"] = paths.WINDIVERT_DLL

        self.log_q = queue.Queue()
        self.bot = None
        self.candidates = []
        self.t_start = None
        self.tray = None
        self._tray_visible = False
        self.f_big = ctk.CTkFont(family="微软雅黑", size=19, weight="bold")
        self.f = ctk.CTkFont(family="微软雅黑", size=13)
        self.f_small = ctk.CTkFont(family="微软雅黑", size=12)
        self.f_log = ctk.CTkFont(family="微软雅黑", size=12)

        self._build_ui()
        self._register_hotkeys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._tick)

    # ---------------- 托盘 ----------------
    def _make_tray_icon(self):
        import pystray
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((2, 2, 62, 62), fill=(240, 240, 240, 255))
        d.pieslice((2, 2, 62, 62), 90, 270, fill=(28, 28, 32, 255))
        d.ellipse((33, 25, 47, 39), fill=(28, 28, 32, 255))
        d.ellipse((17, 25, 31, 39), fill=(240, 240, 240, 255))

        menu = pystray.Menu(
            pystray.MenuItem("显示主窗口", lambda: self.after(0, self._restore_from_tray),
                             default=True),
            pystray.MenuItem("停止任务 (F10)", lambda: self.after(0, self.stop)),
            pystray.MenuItem("退出程序", lambda: self.after(0, self._quit_app)),
        )
        self.tray = pystray.Icon(
            "TaijiFisher", img,
            "太极炸鱼助手（运行中）\nF9 暂停 · F10 停止 · F12 紧急解限",
            menu)
        self.tray.run_detached()

    def _hide_to_tray(self):
        if not self._tray_visible:
            if self.tray is None:
                self._make_tray_icon()
            self.withdraw()
            self._tray_visible = True
            self._log("已最小化到托盘，任务继续运行；左键托盘图标恢复窗口")

    def _restore_from_tray(self):
        if self._tray_visible:
            self.deiconify()
            self.lift()
            self.focus_force()
            self._tray_visible = False

    def _on_close(self):
        """任务运行中点 × = 缩进托盘（防误杀限速进程）；空闲才真退出。"""
        if self.bot and self.bot.is_alive():
            self._hide_to_tray()
        else:
            self._quit_app()

    def _quit_app(self):
        if self.bot and self.bot.is_alive():
            self.bot.stop()
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.destroy()

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = {"padx": 14, "pady": (6, 0)}

        # ---- 应用标题 ----
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkLabel(head, text="太极炸鱼助手", font=self.f_big,
                     text_color="#e8eaed").pack(side="left")
        ctk.CTkLabel(head, text="限速卡CD · 自动施放 · 定时收工",
                     font=self.f_small, text_color="#6b7280").pack(
            side="left", padx=12, pady=(6, 0))
        ctk.CTkLabel(head, text="yysls", font=self.f_small,
                     text_color="#4dd882").pack(side="right", pady=(6, 0))

        # ---- 进程识别行 ----
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", **pad)
        ctk.CTkButton(row, text="扫描游戏进程", width=130, height=32,
                      font=self.f, command=self._scan).pack(side="left")
        self.lb_target = ctk.CTkLabel(
            row, text="未扫描（自动识别进程：yysls）", font=self.f_small,
            text_color="#4dd882", anchor="w", wraplength=520, justify="left")
        self.lb_target.pack(side="left", padx=12, fill="x", expand=True)

        # ---- 参数卡 ----
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        card.pack(fill="x", padx=14, pady=(10, 0))
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=14)
        self.vars = {}

        def field(r, c, label, key, width=110, scale=1.0):
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=r, column=c, padx=(0, 18), pady=5, sticky="w")
            ctk.CTkLabel(cell, text=label, font=self.f_small,
                         text_color="#9aa3ad").pack(anchor="w")
            val = self.cfg[key]
            if scale != 1.0:
                val = float(val) / scale
            var = ctk.StringVar(value=str(val))
            ctk.CTkEntry(cell, textvariable=var, width=width, height=30,
                         font=self.f).pack(anchor="w")
            self.vars[key] = var
            return var

        field(0, 0, "限速 KB/s", "rate_bps", scale=1024.0)
        field(0, 1, "限速时长（秒）", "throttle_seconds")
        field(0, 2, "解限时长（秒）", "release_seconds")
        field(1, 0, "技能键", "cast_key", width=70)
        field(1, 1, "施放间隔（秒）", "cast_interval")
        field(1, 2, "循环次数（0=无限）", "cycles")

        cell = ctk.CTkFrame(grid, fg_color="transparent")
        cell.grid(row=2, column=0, padx=(0, 18), pady=5, sticky="w")
        ctk.CTkLabel(cell, text="定时停止（分钟，0=不停）", font=self.f_small,
                     text_color="#9aa3ad").pack(anchor="w")
        var = ctk.StringVar(value=str(self.cfg["stop_after_minutes"]))
        ctk.CTkEntry(cell, textvariable=var, width=110, height=30,
                     font=self.f).pack(anchor="w")
        self.vars["stop_after_minutes"] = var

        cell2 = ctk.CTkFrame(grid, fg_color="transparent")
        cell2.grid(row=2, column=1, columnspan=2, pady=5, sticky="w")
        ctk.CTkLabel(cell2, text="输入模式", font=self.f_small,
                     text_color="#9aa3ad").pack(anchor="w")
        self.seg_mode = ctk.CTkSegmentedButton(
            cell2, values=list(MODE_DISPLAY.values()),
            font=self.f_small, height=30,
            selected_color="#3b6ea5", selected_hover_color="#4a80bd",
            unselected_color="#33343a", unselected_hover_color="#3d3e46")
        self.seg_mode.set(MODE_DISPLAY.get(self.cfg["input_mode"],
                                           "前台模式（推荐）"))
        self.seg_mode.pack(anchor="w")

        # ---- 控制按钮行 ----
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=14, pady=12)
        self.btn_start = ctk.CTkButton(
            ctrl, text="▶  开始 (F9)", width=150, height=40, font=self.f_big,
            fg_color="#2f9e63", hover_color="#37b573", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_stop = ctk.CTkButton(
            ctrl, text="■  停止 (F10)", width=130, height=40, font=self.f,
            fg_color="#3a3b41", hover_color="#4a4b52", command=self.stop,
            state="disabled")
        self.btn_stop.pack(side="left", padx=10)
        self.btn_panic = ctk.CTkButton(
            ctrl, text="⚡ 紧急解限 (F12)", width=150, height=40, font=self.f,
            fg_color="#c25a3a", hover_color="#d96a45", command=self.panic)
        self.btn_panic.pack(side="left")

        # ---- 状态卡 ----
        stat = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        stat.pack(fill="x", padx=14)
        inner = ctk.CTkFrame(stat, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(10, 4))
        self.lb_state = ctk.CTkLabel(inner, text="状态：待机", font=self.f_big,
                                     text_color="#9aa3ad")
        self.lb_state.pack(side="left")
        self.lb_stats = ctk.CTkLabel(inner, text="", font=self.f_small,
                                     text_color="#9aa3ad")
        self.lb_stats.pack(side="right")
        self.bar = ctk.CTkProgressBar(stat, height=8, corner_radius=4,
                                      progress_color="#f0c04a")
        self._bar_total = 0
        self.bar.pack(fill="x", padx=16, pady=(2, 10))
        self.bar.set(0)

        # ---- 日志卡 ----
        logf = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        logf.pack(fill="both", expand=True, padx=14, pady=12)
        ctk.CTkLabel(logf, text="日志", font=self.f_small,
                     text_color="#9aa3ad").pack(anchor="w", padx=16, pady=(10, 2))
        self.txt = ctk.CTkTextbox(logf, font=self.f_log, fg_color="#191a1e",
                                  wrap="none")
        self.txt.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for tag, color in (("warn", "#f0a643"), ("err", "#ff6b6b"),
                           ("ok", "#4dd882")):
            self.txt.tag_config(tag, foreground=color)

    # ---------------- 热键 ----------------
    def _register_hotkeys(self):
        try:
            import keyboard
            keyboard.add_hotkey("f9", lambda: self.after(0, self._hotkey_f9))
            keyboard.add_hotkey("f10", lambda: self.after(0, self.stop))
            keyboard.add_hotkey("f12", lambda: self.after(0, self.panic))
        except Exception as exc:
            self._log("全局热键注册失败(不影响按钮操作): %r" % exc, "warn")

    def _hotkey_f9(self):
        if self.bot and self.bot.is_alive():
            self.bot.toggle_pause()
        else:
            self.start()

    # ---------------- 逻辑 ----------------
    def _scan(self):
        self.candidates = gameproc.find_processes(PROCESS_KEYWORDS)
        if not self.candidates:
            self.lb_target.configure(text="没找到 yysls 进程，确认游戏已启动",
                                     text_color="#f0a643")
            return
        desc = []
        for pid, name, title, _exe in self.candidates:
            flows = gameproc.scan_flows(pid)
            desc.append("%s(pid %d) %s" % (name, pid,
                                           gameproc.describe_flows(*flows)))
        self.lb_target.configure(text="；".join(desc), text_color="#4dd882")

    def _collect_cfg(self):
        cfg = dict(self.cfg)
        cfg["input_mode"] = MODE_INTERNAL.get(self.seg_mode.get(), "foreground")
        for key, var in self.vars.items():
            val = var.get().strip()
            if key == "rate_bps":
                cfg[key] = max(0.0625, float(val or 1)) * 1024.0
            elif key in ("cast_interval", "stop_after_minutes", "jitter"):
                cfg[key] = float(val or 0)
            elif key in ("throttle_seconds", "release_seconds", "cycles"):
                cfg[key] = int(float(val or 0))
            else:
                cfg[key] = val
        # 内部运行路径不入配置（打包模式下 _MEI 每次启动都会变）
        cfg["windivert_dll"] = paths.WINDIVERT_DLL
        return cfg

    def _save_cfg(self, cfg):
        # windivert_dll 是每次运行才确定的内部路径，绝不写入配置文件
        cfg = {k: v for k, v in cfg.items() if k != "windivert_dll"}
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def start(self):
        if self.bot and self.bot.is_alive():
            return
        cfg = self._collect_cfg()
        self._save_cfg(cfg)
        self.bot = FishBot(cfg, log=self._log, on_state=self._on_state)
        self.bot.start()
        self.t_start = time.monotonic()
        self.btn_stop.configure(state="normal", fg_color="#b8433a",
                                hover_color="#d15048")
        self._bar_total = float(cfg["stop_after_minutes"]) * 60.0
        self._log("已开始。热键：F9 暂停/继续 · F10 停止 · F12 紧急解限")
        # 前台模式：bot 先置前游戏，随后助手缩进托盘；后台模式：直接缩托盘
        self.after(1500, self._minimize_for_mode)

    def _minimize_for_mode(self):
        if not (self.bot and self.bot.is_alive()):
            return
        self._hide_to_tray()

    def stop(self):
        if self.bot:
            self.bot.stop()

    def panic(self):
        if self.bot and self.bot.is_alive():
            self._log("【紧急解限】立即恢复网络并停止", "warn")
            self.bot.stop(emergency=True)
        else:
            self._log("机器人未在运行", "warn")

    def _on_state(self, state=None, **kw):
        def upd():
            color, label = STATE_STYLE.get(state, ("#9aa3ad", str(state)))
            self.lb_state.configure(text="状态：%s" % label, text_color=color)
        self.after(0, upd)

    def _log(self, msg, level="info"):
        self.log_q.put((msg, level))

    # ---------------- 周期刷新 ----------------
    def _tick(self):
        now = time.monotonic()
        try:
            while True:
                msg, level = self.log_q.get_nowait()
                tag = {"warn": "warn", "error": "err"}.get(level)
                self.txt.configure(state="normal")
                stamp = time.strftime("%H:%M:%S")
                self.txt.insert("end", "[%s] %s\n" % (stamp, msg))
                if tag:
                    self.txt.tag_add(tag, "end-2l", "end-1l")
                self.txt.see("end")
                self.txt.configure(state="disabled")
        except queue.Empty:
            pass

        alive = self.bot and self.bot.is_alive()
        if alive:
            elapsed = now - (self.t_start or now)
            mins, secs = divmod(int(elapsed), 60)
            stats = "已运行 %02d:%02d   施放 %d 次   已完成 %d 轮" % (
                mins, secs, self.bot.casts, self.bot.cycle)
            self.lb_stats.configure(text=stats)
            if self._bar_total > 0:
                remain = max(0.0, self._bar_total - elapsed)
                self.bar.set(min(1.0, elapsed / self._bar_total))
                rm, rs = divmod(int(remain + 0.999), 60)
                self.bar.configure(progress_color="#ff7a66"
                                   if remain < self._bar_total * 0.2 else "#f0c04a")
                self.lb_stats.configure(text=stats + "   距定时停止 %02d:%02d"
                                        % (rm, rs))
            else:
                self.bar.set(0)
        elif self.bot and not alive and self.btn_stop.cget("state") == "normal":
            self.btn_stop.configure(state="disabled", fg_color="#3a3b41",
                                    hover_color="#4a4b52")
            self.bar.set(0)
            if self._tray_visible:
                self._log("任务已结束，从托盘恢复窗口")
                self._restore_from_tray()
        self.after(150, self._tick)


def run_gui():
    app = App()
    app.mainloop()
