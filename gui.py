# -*- coding: utf-8 -*-
"""太极炸鱼助手 · Qt 界面（PySide6）。

从 customtkinter 迁到 Qt 的原因：CTk 的按钮主题只有单一 fg_color，同控件
多语义（主操作/危险操作）只能逐个实例硬改色；Qt 的 QSS 支持 #id 选择器与
:hover/:pressed/:disabled 伪态，一套样式表就能表达完整状态机。

界面约定：
  - 所有色值/间距/字号只在 theme.py 定义，本文件不出现裸数值
  - 竖版单列：辅助按钮 → 参数（常显）→ 监视卡（操作条 → 状态行 → 进度条 → 日志抽屉）
  - 参数六行共用一个 QGridLayout，标签列与输入框列的左右边缘全窗口对齐
  - 输入框定宽（120/72），不随窗口拉宽；窗口尺寸由 sizeHint 算出
  - 日志框垂直策略 Ignored，不参与 sizeHint，否则 QTextEdit 默认 192px 会把窗口顶高

托盘：
  点 × 时若任务在跑 → 缩托盘（防误杀限速进程）；空闲则直接退出
  「最小化到托盘」按钮可随时手动缩托盘，不等开始任务
  托盘左键/双击恢复窗口，右键菜单可显示/停止/退出
"""
import html
import json
import os
import queue
import sys
import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)

import gameproc
import paths
import theme as TH
from bot import FishBot

CONFIG_PATH = paths.CONFIG_PATH
ICON_PATH = paths.ICON_PATH
ICON_PNG = os.path.join(paths.ASSETS_DIR, "icon_src.png")

# 游戏进程识别关键字（燕云十六声客户端进程名含 yysls）
PROCESS_KEYWORDS = ["yysls"]

DEFAULT_CFG = {
    "process_keywords": PROCESS_KEYWORDS,
    "rate_bps": 512.0,          # 0.5 KB/s，实测可用值
    "throttle_seconds": 600,    # 限速期 10 分钟
    "release_seconds": 10,      # 解限恢复 10 秒
    "cast_key": "1",
    "cast_interval": 1.0,       # 限速态 CD 卡 1 秒，间隔 1 秒刚好
    "cycles": 0,
    "stop_after_minutes": 0,
    "jitter": 0.15,
    "input_mode": "postmessage",  # 只保留后台模式
    "flow_refresh_seconds": 5,
    "windivert_dll": paths.WINDIVERT_DLL,
}

# 阶段 -> (颜色键, 说明)
STATE_STYLE = {
    FishBot.IDLE: ("onSurfaceVariant", "待机"),
    FishBot.THROTTLE: ("error", "限速炸鱼中"),
    FishBot.RELEASE: ("success", "解限恢复中"),
    FishBot.WAITING: ("primary", "等待游戏连接"),
    FishBot.PAUSED: ("primary", "已暂停"),
    FishBot.STOPPED: ("onSurfaceVariant", "已停止"),
    FishBot.ERROR: ("error", "出错"),
}

# 输入校验规则：key -> (中文名, 最小值, 是否必须 > 最小值, 是否整数)
FIELD_RULES = {
    "rate_bps": ("限速 KB/s", 0.0625, True, False),
    "throttle_seconds": ("限速时长", 1, True, True),
    "release_seconds": ("解限时长", 1, True, True),
    "cast_interval": ("施放间隔", 0.1, True, False),
    "stop_after_minutes": ("定时停止", 0, False, False),
}


def state_color(state):
    key = STATE_STYLE.get(state, ("onSurfaceVariant", str(state)))[0]
    return TH.c(key)


# ---------------- 组件小工具 ----------------
def make_card(fixed_v=False):
    """卡片容器。fixed_v=False 时垂直 Expanding —— 两栏才会自动同高。"""
    f = QFrame()
    f.setObjectName("card")
    f.setSizePolicy(QSizePolicy.Preferred,
                    QSizePolicy.Fixed if fixed_v else QSizePolicy.Expanding)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(TH.SP["sm"], TH.SP["sm"], TH.SP["sm"], TH.SP["sm"])
    lay.setSpacing(TH.SP["xs"])
    return f, lay


def group_title(text):
    lb = QLabel(text)
    lb.setObjectName("group")
    return lb


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("太极炸鱼助手 · 燕云十六声")
        if os.path.isfile(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.cfg = dict(DEFAULT_CFG)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self.cfg.update(json.load(f))
        except Exception:
            pass
        # 前台模式已从界面移除：旧配置里的 foreground 一律归正为后台
        self.cfg["input_mode"] = "postmessage"
        # 旧配置可能存有过期的一次性解包路径，强制用本次运行的真实路径
        self.cfg["windivert_dll"] = paths.WINDIVERT_DLL

        self.q = queue.Queue()
        self.bot = None
        self.tray = None
        self.t_start = None
        self._bar_total = 0.0
        self._last_state = FishBot.IDLE
        self._h_no_log = 0
        self._h_log = 0

        # 先建托盘：_build_ui 里要根据托盘是否存在决定「最小化到托盘」按钮的可用状态
        self._build_tray()
        self._build_ui()
        self._last_scan_ok = None      # 上次自动扫描结果，用于只在状态翻转时写日志
        # 先扫一次再量尺寸：目标行文本长短会变（"正在查找" → "没找到…" 或进程名），
        # 顺序反了窗口会按临时文案定高，实际文本一变就换行。
        self._auto_scan(quiet=False)
        self._fit_to_content()
        self._root.setFocus()
        self._scan_at = time.monotonic()   # 上次自动扫描时刻，_tick 里按 3 秒节流

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(120)

    def _fit_to_content(self):
        """窗口尺寸由内容决定，不写死数字。

        日志默认收起：日常形态就是「状态 + 操作 + 参数」，窗口只装这些。
        点「日志」时临时加高，收起后收回原高。两态高度各量一次存起来。
        """
        self.log.setVisible(False)
        hint_no_log = self.sizeHint()

        # 展开态高度不能靠「临时显示再 sizeHint()」量：同一轮里 setVisible 之后
        # 布局还没重新计算，sizeHint() 会返回收起态的值（踩过，两次都是同一个数）。
        # 直接算：收起态高度 + 日志框最小高度 + 卡片内外边距。
        self._h_no_log = hint_no_log.height()
        self._h_log = (hint_no_log.height()
                       + self.log.minimumHeight()
                       + TH.SP["sm"] * 2
                       + TH.SP["sm"])

        self.setMinimumSize(hint_no_log.width(), self._h_no_log)
        self.resize(hint_no_log.width() + TH.SP["md"],
                    self._h_no_log + TH.SP["md"])

    # ---------------- 托盘 ----------------
    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = QIcon(ICON_PATH) if os.path.isfile(ICON_PATH) else self.windowIcon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("太极炸鱼助手")
        menu = QMenu(self)
        act_show = QAction("显示主窗口", self)
        act_show.triggered.connect(self._restore_from_tray)
        act_stop = QAction("停止任务 (F10)", self)
        act_stop.triggered.connect(self.stop)
        act_quit = QAction("退出程序", self)
        act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_show)
        menu.addAction(act_stop)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _hide_to_tray(self):
        if self.tray is None:
            return
        self.tray.show()
        self.hide()
        self._log("已最小化到托盘，任务继续运行；左键托盘图标恢复窗口")

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---------------- 窗口生命周期 ----------------
    def closeEvent(self, ev):
        """点 × ：任务在跑就缩托盘（防误杀限速进程），空闲才真退出。"""
        if self.bot and self.bot.is_alive():
            ev.ignore()
            self._hide_to_tray()
        else:
            self._quit_app()
            ev.accept()

    def _quit_app(self):
        if self.bot and self.bot.is_alive():
            self.bot.stop()
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()

    # ---------------- 界面 ----------------
    def _build_ui(self):
        """竖版单列：操作条 → 辅助按钮 → 参数（常显）→ 监视卡。

        为什么改竖版：横版两栏是把窗口摊宽，挂机时窗口常年在屏幕角落，
        窄而高更省地方。参数一天设一次但不能藏 —— 藏起来就得先点开才能确认
        技能键对不对，反而多一步。日志平时不看，做成抽屉收在最底下。

        开始/暂停/停止放在待机状态行正上方（同一张监视卡内），
        眼睛从按钮往下扫一眼就是状态；参数常显在中间；
        日志收在同一张卡的最底下，标题本身就是开关，不另设按钮。
        """
        root = QWidget()
        # 让根容器可以接焦点：开窗时把焦点放在它身上，第一个输入框就不会一上来
        # 就带一圈金色焦点框（看着像「已经选中了这一格」）。
        root.setFocusPolicy(Qt.StrongFocus)
        self._root = root
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(TH.SP["md"], TH.SP["md"], TH.SP["md"], TH.SP["md"])
        outer.setSpacing(TH.SP["sm"])

        # ---- 目标行：自动显示当前瞄准的进程，不需要手动扫描 ----
        # 进程识别本来就是后台每轮都在做的事（bot._pick_process），界面这里只是
        # 把它显示出来，没有任何「必须先扫一次」的前置条件。所以不放按钮：
        # 空闲时每 3 秒自动刷一次，任务运行时由 bot 自己找，界面只跟着显示。
        self.lb_target = QLabel("正在查找 yysls…")
        self.lb_target.setObjectName("caption")
        self.lb_target.setWordWrap(True)
        # 最多两行：多出来的省略，窗口高度不跟着文本长度跳
        self.lb_target.setMaximumHeight(TH.TYPE["caption"] * 2 + TH.SP["sm"])
        outer.addWidget(self.lb_target)

        # ---- 参数（常显，三组竖排，共用一张网格）----
        # 三组共用一个 QGridLayout：label 列宽取三组里最长的那个，输入框列宽统一，
        # 六行字段的左边缘与右边缘全部对齐。分组各自建 grid 会各算各的列宽，
        # 结果每组输入框起始 x 都不一样，竖版窄窗口里一眼就看出参差。
        par_card, par_lay = make_card(fixed_v=True)
        grid = QGridLayout()
        grid.setHorizontalSpacing(TH.SP["sm"])
        grid.setVerticalSpacing(TH.SP["xs"])
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        par_lay.addLayout(grid)
        self.vars = {}
        row = 0

        def cell(key, scale=1.0):
            """生成一个已填好当前值的 QLineEdit，并登记到 self.vars。"""
            val = self.cfg.get(key, DEFAULT_CFG.get(key, ""))
            if isinstance(val, (int, float)):
                if scale != 1.0:
                    val = float(val) / scale
                text = "%g" % val          # 去掉 0.00048828125 这类浮点噪声
            else:
                text = str(val)
            ed = QLineEdit(text)
            ed.setFixedHeight(TH.CTRL["md"])
            ed.setFixedWidth(120)      # 六行同宽，右边缘才齐
            self.vars[key] = ed
            return ed

        def add_group(title, specs):
            nonlocal row
            if row:
                # 组间留白用行最小高度，不要塞空 QLabel —— QLabel 会按 QWidget 的
                # 样式刷一层 surface 底色，在卡片（surfaceContainerLow）上显出一条亮带。
                grid.setRowMinimumHeight(row, TH.SP["md"])
                row += 1
            grid.addWidget(group_title(title), row, 0, 1, 2)
            row += 1
            for cap, ed in specs:
                lb = QLabel(cap)
                lb.setObjectName("body")
                grid.addWidget(lb, row, 0, Qt.AlignLeft | Qt.AlignVCenter)
                grid.addWidget(ed, row, 1, Qt.AlignLeft)
                row += 1

        add_group("限速", [
            ("限速 KB/s", cell("rate_bps", scale=1024.0)),
            ("限速时长（秒）", cell("throttle_seconds")),
        ])
        add_group("施放", [
            ("施放间隔（秒）", cell("cast_interval")),
            ("技能键", cell("cast_key")),
        ])
        add_group("恢复", [
            ("解限时长（秒）", cell("release_seconds")),
            ("定时停止（分钟，0=不停）", cell("stop_after_minutes")),
        ])
        outer.addWidget(par_card)

        # ---- 底部监视卡：操作条 → 状态行 → 进度条 → 日志抽屉 ----
        # 开始/暂停/停止放在待机行正上方：按钮和「现在什么状态」是同一件事的两面，
        # 眼睛从按钮往下扫一眼就是状态，不用在窗口两端来回找。
        self.mon_card, mon_lay = make_card(fixed_v=True)

        # 三个按钮平分整行：卡内宽度固定（由参数卡撑出来），平分后右边缘与卡片内边距
        # 对齐，右侧不留空带。宽度跟文字走会留一截白，比按钮略宽更不工整。
        # 暂停与停止带热键后缀：挂机时窗口常缩在托盘，只能靠热键操作，标注必须留在按钮上。
        act = QHBoxLayout()
        act.setSpacing(TH.SP["xs"])
        self.btn_start = QPushButton("开始")
        self.btn_start.setObjectName("hero")
        self.btn_start.clicked.connect(self.start)
        self.btn_pause = QPushButton("暂停 F9")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_stop = QPushButton("停止 F10")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        btns = (self.btn_start, self.btn_pause, self.btn_stop)
        for b in btns:
            b.setFixedHeight(TH.CTRL["sm"])
            act.addWidget(b, 1)   # stretch=1：三者等分整行，右侧不留白
        mon_lay.addLayout(act)

        r1 = QHBoxLayout()
        r1.setSpacing(TH.SP["xs"])
        self.lb_state = QLabel("待机")
        self.lb_state.setObjectName("state")
        r1.addWidget(self.lb_state)

        self.badge = QLabel("未连接")
        self.badge.setObjectName("badge_off")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedHeight(TH.CTRL["sm"])
        r1.addWidget(self.badge, 0, Qt.AlignVCenter)
        r1.addStretch()

        cap_runtime = QLabel("已运行")
        cap_runtime.setObjectName("caption")
        r1.addWidget(cap_runtime)
        self.lb_runtime = QLabel("00:00")
        self.lb_runtime.setObjectName("metric")
        r1.addWidget(self.lb_runtime)
        mon_lay.addLayout(r1)

        self.bar = QProgressBar()
        self.bar.setFixedHeight(TH.CTRL["bar"])
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        mon_lay.addWidget(self.bar)

        # 日志抽屉（监视卡内）：标题本身就是开关，不另设按钮
        self.log_card, log_lay = make_card(fixed_v=False)
        # 收起态锁成 Fixed：卡片默认 Expanding，窗口比 sizeHint 高出的那十几像素
        # 会全落到它身上，标题底下白多一条空带（实测 48 → 64）。展开时再放开。
        self.log_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        log_head = QHBoxLayout()
        log_head.setSpacing(TH.SP["xs"])
        self.btn_log = QPushButton("▸ 运行日志")
        self.btn_log.setObjectName("drawer")
        self.btn_log.setCheckable(True)
        self.btn_log.setFixedHeight(TH.CTRL["sm"])
        self.btn_log.toggled.connect(self._toggle_log)
        log_head.addWidget(self.btn_log, 1)
        # 「最小化到托盘」跟日志标题同一行、靠右：两者都是「不常点但随时要有」的次级动作，
        # 借日志这一行安置，比在窗口顶部单独占一行更不占地方，也不抢主操作的视线。
        self.btn_tray = QPushButton("最小化到托盘")
        self.btn_tray.setObjectName("tool")
        self.btn_tray.clicked.connect(self._hide_to_tray)
        self.btn_tray.setEnabled(self.tray is not None)
        self.btn_tray.setFixedHeight(TH.CTRL["sm"])
        self.btn_tray.setCursor(Qt.PointingHandCursor)
        log_head.addWidget(self.btn_tray, 0)
        log_lay.addLayout(log_head)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        # 日志框不参与「窗口该多大」的计算：QTextEdit 默认 sizeHint 约 192px 高，
        # 会把窗口一路顶高。垂直策略设为 Ignored 后 sizeHint 阶段只按最小高度算，
        # 实际显示时它仍会吃满剩余空间。
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.log.setMinimumHeight(TH.CTRL["lg"] * 5)
        self.log.setVisible(False)
        log_lay.addWidget(self.log, 1)
        # 日志卡 stretch 给 0：自己不抢多余高度。收起时它就是「标题那 24px + 卡片内边距」，
        # 多给 1 会让它在窗口 resize 时吃掉十几像素，标题下露出一条空带。
        # 展开时日志框是 Expanding 策略，多余高度自然落到它身上。
        mon_lay.addWidget(self.log_card, 0)
        outer.addWidget(self.mon_card)

        self._log("界面就绪（Qt + Material 3）")
        self._log("默认：限速 0.5 KB/s · 施放间隔 1 秒 · 后台按键模式")

    def _toggle_log(self, on):
        """展开/收起日志框。状态与进度条始终可见，只有日志正文折叠。"""
        self.log.setVisible(on)
        self.btn_log.setText("▾ 运行日志" if on else "▸ 运行日志")
        # 收起：卡片只留标题那一行，不让它吸收窗口多余高度；展开：放开吃满剩余空间。
        self.log_card.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Expanding if on else QSizePolicy.Fixed)
        if on:
            self.setMinimumHeight(self._h_log)
            if self.height() < self._h_log + TH.SP["md"]:
                self.resize(self.width(), self._h_log + TH.SP["md"])
        else:
            self.setMinimumHeight(self._h_no_log)
            if self.height() > self._h_no_log + TH.SP["md"]:
                self.resize(self.width(), self._h_no_log + TH.SP["md"])

    # ---------------- 热键 ----------------
    def _install_hotkeys(self):
        """全局热键用 keyboard 库；注册失败不影响按钮。"""
        try:
            import keyboard
            keyboard.add_hotkey("f9", lambda: self.q.put(("hotkey", "f9")))
            keyboard.add_hotkey("f10", lambda: self.q.put(("hotkey", "f10")))
        except Exception as exc:
            self._log("全局热键注册失败（不影响按钮操作）: %r" % exc, "warn")

    # ---------------- 日志 ----------------
    def _log(self, msg, level="info"):
        self.q.put(("log", (msg, level)))

    def _append_log(self, msg, level="info"):
        color = {
            "warn": TH.c("primary"),
            "error": TH.c("error"),
            "ok": TH.c("success"),
        }.get(level, TH.c("onSurfaceVariant"))
        stamp = time.strftime("%H:%M:%S")
        text = html.escape("[%s] %s" % (stamp, msg))
        self.log.append('<span style="color:%s">%s</span>' % (color, text))

    def _on_state(self, state=None, **kw):
        """bot 线程回调：只入队，绝不碰 GUI。"""
        self.q.put(("state", state))

    # ---------------- 逻辑 ----------------
    def _auto_scan(self, quiet=True):
        """自动刷新目标行。

        quiet=True 时不写日志、不改徽标（周期性刷新用）；quiet=False 只在
        第一次或状态翻转时用，避免每 3 秒刷一条「没找到」把日志刷爆。
        """
        # 关键字走配置，CLI 的 --keywords 也能生效；没配就退回常量
        kws = self.cfg.get("process_keywords") or PROCESS_KEYWORDS
        cands = gameproc.find_processes(kws)
        if not cands:
            self.lb_target.setText("没找到 %s 进程，请先启动游戏" % "/".join(kws))
            if self._last_scan_ok is not False:
                self._last_scan_ok = False
                self._set_badge(False)
                if not quiet:
                    self._log("没找到 yysls 进程", "warn")
            return
        self._set_badge(True)
        parts = []
        for pid, name, title, _exe in cands:
            tcp4, udp4, tcp6, udp6 = gameproc.scan_flows(pid)
            # 目标行只报「是谁 + 抓到几条」，不逐条列端点：端点会有一长串 IP:端口，
            # 撑成三四行把下面的参数卡往下推，窗口高度跟着跳。明细只在进程刚出现时
            # 写一次日志，否则每 3 秒刷一遍会把日志区冲掉。
            parts.append("%s · pid %d · TCP %d / UDP %d" % (
                name, pid, len(tcp4) + len(tcp6), len(udp4) + len(udp6)))
            if self._last_scan_ok is not True:
                self._log("找到 %s(pid %d)  %s" % (
                    name, pid, gameproc.describe_flows(tcp4, udp4, tcp6, udp6)), "ok")
        self._last_scan_ok = True
        self.lb_target.setText("；".join(parts))

    def _set_badge(self, connected):
        if connected:
            self.badge.setObjectName("badge_on")
            self.badge.setText("已连接 yysls")
        else:
            self.badge.setObjectName("badge_off")
            self.badge.setText("未连接")
        # 换 objectName 后必须重新求值样式表，否则颜色不变
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def _collect_cfg(self):
        """读界面参数。非法输入抛 ValueError（中文说明），由 start() 弹窗。"""
        cfg = dict(self.cfg)
        for key, ed in self.vars.items():
            raw = ed.text().strip()
            if key == "cast_key":
                if not raw:
                    raise ValueError("技能键不能为空，请填一个按键（例如 1）")
                cfg[key] = raw
                continue
            label, min_v, strict, is_int = FIELD_RULES.get(
                key, (key, None, False, False))
            if not raw:
                raise ValueError("%s 不能为空" % label)
            try:
                num = float(raw)
            except ValueError:
                raise ValueError("%s 必须是数字，当前填的是「%s」" % (label, raw))
            if min_v is not None:
                if strict and num < min_v:
                    raise ValueError("%s 必须大于 %s，当前填的是 %s"
                                     % (label, min_v, raw))
                if not strict and num < min_v:
                    raise ValueError("%s 不能小于 %s，当前填的是 %s"
                                     % (label, min_v, raw))
            if is_int and num != int(num):
                raise ValueError("%s 必须是整数，当前填的是 %s" % (label, raw))
            if key == "rate_bps":
                cfg[key] = num * 1024.0
            elif is_int:
                cfg[key] = int(num)
            else:
                cfg[key] = num
        # 前台模式已移除，固定后台；内部路径不入配置（_MEI 每次启动都变）
        cfg["input_mode"] = "postmessage"
        cfg["windivert_dll"] = paths.WINDIVERT_DLL
        return cfg

    def _save_cfg(self, cfg):
        cfg = {k: v for k, v in cfg.items() if k != "windivert_dll"}
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._log("配置保存失败: %r" % exc, "warn")

    def start(self):
        if self.bot and self.bot.is_alive():
            return
        try:
            cfg = self._collect_cfg()
        except ValueError as exc:
            self._log("参数有误：%s" % exc, "error")
            QMessageBox.warning(self, "参数有误", str(exc))
            return
        self._save_cfg(cfg)
        self.bot = FishBot(cfg, log=self._log, on_state=self._on_state)
        self.bot.start()
        self.t_start = time.monotonic()
        self._bar_total = float(cfg["stop_after_minutes"]) * 60.0
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("暂停 F9")
        self.btn_stop.setEnabled(True)
        self._log("已开始：限速 %.4g KB/s，施放间隔 %.4g 秒，后台模式"
                  % (cfg["rate_bps"] / 1024.0, cfg["cast_interval"]), "ok")

    def toggle_pause(self):
        if self.bot and self.bot.is_alive():
            self.bot.toggle_pause()
            self.btn_pause.setText(
                "继续 F9" if self.btn_pause.text() == "暂停 F9" else "暂停 F9")

    def stop(self):
        if self.bot and self.bot.is_alive():
            self.bot.stop()

    # ---------------- 周期刷新 ----------------
    def _tick(self):
        # 1) 排空消息队列
        while True:
            try:
                kind, payload = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(*payload)
            elif kind == "state":
                self._last_state = payload
                self._render_state(payload)
            elif kind == "hotkey":
                # 开始不配热键（用户明确要求）：F9 只在任务运行时暂停/继续，
                # 空闲时按 F9 什么也不做，避免误触把任务点起来。
                if payload == "f9":
                    if self.bot is not None and self.bot.is_alive():
                        self.toggle_pause()
                else:
                    self.stop()

        alive = self.bot is not None and self.bot.is_alive()

        # 2) 空闲时每 3 秒自动刷新目标行（任务运行时由 bot 自己找进程，界面不插手）
        if not alive and time.monotonic() - self._scan_at >= 3.0:
            self._scan_at = time.monotonic()
            self._auto_scan(quiet=True)

        # 3) 运行时长 + 进度条
        if alive:
            elapsed = time.monotonic() - (self.t_start or time.monotonic())
            mins, secs = divmod(int(elapsed), 60)
            self.lb_runtime.setText("%02d:%02d" % (mins, secs))
            if self._bar_total > 0:
                remain = max(0.0, self._bar_total - elapsed)
                self.bar.setRange(0, 100)
                self.bar.setValue(int(min(1.0, elapsed / self._bar_total) * 100))
            else:
                # 无限循环没有总时长：用原生忙碌条表示"还活着"
                if self.bar.maximum() != 0:
                    self.bar.setRange(0, 0)
        else:
            if self.bar.maximum() == 0:
                self.bar.setRange(0, 100)
            self.bar.setValue(0)

        # 4) 任务结束后复位按钮、把窗口从托盘捞回来
        if self.bot is not None and not alive:
            if self.btn_stop.isEnabled():
                self.btn_start.setEnabled(True)
                self.btn_pause.setEnabled(False)
                self.btn_pause.setText("暂停 F9")
                self.btn_stop.setEnabled(False)
                self.bar.setRange(0, 100)
                self.bar.setValue(0)
            if not self.isVisible() and self.tray is not None:
                self._log("任务已结束，从托盘恢复窗口")
                self._restore_from_tray()

    def _render_state(self, state):
        label = STATE_STYLE.get(state, ("onSurfaceVariant", str(state)))[1]
        self.lb_state.setText(label)
        self.lb_state.setStyleSheet("color: %s;" % state_color(state))


def run_gui():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(TH.build_qss())
    app.setQuitOnLastWindowClosed(False)  # 缩托盘后窗口隐藏不应退出进程
    win = App()
    win.show()
    win._install_hotkeys()
    return app.exec()
