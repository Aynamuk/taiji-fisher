# -*- coding: utf-8 -*-
"""界面主题：Material Design 3 语义色 + 刻度常量 + QSS。

色值不是手调的，是 Material 3 官方算法（materialyoucolor）以游戏图标金
#C9A227 为种子色算出来的 31 个语义角色。这里把它们固化成字面量，
运行时不依赖 materialyoucolor —— 只在换种子色时重新生成一次即可。

重新生成方法（改 SEED 后跑一遍，把输出贴回 M3）：
    from materialyoucolor.scheme.scheme_neutral import SchemeNeutral
    from materialyoucolor.scheme.scheme_vibrant import SchemeVibrant
    from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
    from materialyoucolor.hct import Hct
    scheme = SchemeNeutral(Hct.from_int(0xFFC9A227), True, 0.0)
    MaterialDynamicColors.primary.get_argb(scheme) & 0xFFFFFF   # -> 0xFFD971

分工：
  表面/文字 取 SchemeNeutral（纯中性灰，不会偏色）
  强调/危险 取 SchemeVibrant（高饱和，主按钮才跳得出来）
"""

SEED = 0xFFC9A227  # 品牌种子色：游戏图标金

M3 = {
    # ---- 表面层（由低到高，靠色阶分层，不靠描边）----
    "surface": "#0F0E0C",
    "surfaceDim": "#0F0E0C",
    "surfaceBright": "#2E2C27",
    "surfaceContainerLowest": "#000000",
    "surfaceContainerLow": "#141311",
    "surfaceContainer": "#1B1916",
    "surfaceContainerHigh": "#211F1C",
    "surfaceContainerHighest": "#282521",
    # ---- 文字 ----
    "onSurface": "#EBE4DE",
    "onSurfaceVariant": "#AFAAA4",
    "outline": "#79756F",
    "outlineVariant": "#4B4743",
    "inverseSurface": "#FEF8F5",
    "inverseOnSurface": "#575552",
    # ---- 强调 ----
    "primary": "#FFD971",
    "onPrimary": "#614C00",
    "primaryContainer": "#FCC800",
    "onPrimaryContainer": "#574300",
    "tertiary": "#FAFFAD",
    "onTertiary": "#5E6400",
    # ---- 危险 ----
    "error": "#FF7351",
    "onError": "#450900",
    "errorContainer": "#B92902",
    "onErrorContainer": "#FFD2C8",
    # ---- 派生（M3 Blend.cam16_ucs 算的 hover/pressed，不是随手调亮）----
    "primaryHover": "#FCDB86",
    "primaryPressed": "#F8DD9A",
    "errorHover": "#D3674C",
    # ---- 成功（Blend.harmonize 把绿拉到种子色相后取 tone）----
    "successContainer": "#2C5000",
    "onSuccessContainer": "#B1F668",
    "success": "#96D94F",
}

# 间距：4px 基准，只用这几档。Fluent 2 的完整 ramp 里 2/6/10 是给图标对齐留的，
# 本程序不用图标对齐，故不引入，保证任何间距都是 4 的倍数。
SP = {"xxs": 4, "xs": 8, "sm": 12, "md": 16, "lg": 24, "xl": 32}

# 圆角：上限 16px（超过会显得廉价）
RAD = {"sm": 4, "md": 8, "lg": 12, "xl": 16}

# 控件高度（紧凑档）：正文 14px 配控件 28px = 2.0 倍，比 Windows 标准的
# 32px（2.29 倍）再收紧一档；主操作按钮 32px 就是标准高度，不再往上加。
# 界面里只有三种高度，不许出现第四种。
CTRL = {"sm": 24, "md": 28, "lg": 32, "bar": 4}

# 字号：只取 Windows 11 Type Ramp 里的档位，不自己造数
#   caption 12/16 · body 14/20 · body large 18/24 · subtitle 20/28
#   title 28/36 · title large 40/52 · display 68/92
# 紧凑版把页头压到 subtitle 20、状态压到 large 18，最大字号不超 20。
TYPE = {"caption": 12, "body": 14, "large": 18, "subtitle": 20,
        "title": 28, "display": 40}

FONT_FAMILY = "Microsoft YaHei UI"
FONT_MONO = '"Cascadia Mono", "Consolas", monospace'


def c(key: str) -> str:
    """取语义色。键不存在直接 KeyError —— 宁可当场崩，不要静默变黑。"""
    return M3[key]


def build_qss(t: dict = None) -> str:
    t = t or M3
    return f"""
    QWidget {{
        background: {t['surface']};
        color: {t['onSurface']};
        font-family: "{FONT_FAMILY}";
        font-size: {TYPE['body']}px;
    }}

    QFrame#card {{
        background: {t['surfaceContainerLow']};
        border: none;
        border-radius: {RAD['lg']}px;
    }}

    /* QLabel 必须显式透明：QWidget 那条 background 会一并套到 QLabel 上，
       卡片里的每个标签都会刷出一块窗口底色，在卡片上形成一条条暗带。 */
    QLabel {{ background: transparent; }}

    QLabel#h1       {{ font-size: {TYPE['subtitle']}px; font-weight: 600; }}
    QLabel#metric   {{ font-size: {TYPE['large']}px; font-weight: 600;
                       color: {t['primary']}; }}
    QLabel#state    {{ font-size: {TYPE['large']}px; font-weight: 600; }}
    QLabel#caption  {{ color: {t['onSurfaceVariant']};
                       font-size: {TYPE['caption']}px; }}
    QLabel#body     {{ color: {t['onSurfaceVariant']};
                       font-size: {TYPE['caption']}px; }}
    QLabel#group    {{ color: {t['primary']}; font-size: {TYPE['caption']}px;
                       font-weight: 600; }}

    QLabel#badge_off {{
        color: {t['onSurfaceVariant']}; background: {t['surfaceContainerHigh']};
        border-radius: {RAD['lg']}px; padding: 0 {SP['sm']}px;
        font-size: {TYPE['caption']}px;
    }}
    QLabel#badge_on {{
        color: {t['onSuccessContainer']}; background: {t['successContainer']};
        border-radius: {RAD['lg']}px; padding: 0 {SP['sm']}px;
        font-size: {TYPE['caption']}px;
    }}

    QLineEdit {{
        background: {t['surfaceContainerHigh']};
        border: 1px solid transparent;
        border-radius: {RAD['md']}px;
        padding-left: {SP['sm']}px; padding-right: {SP['sm']}px;
        color: {t['onSurface']};
        font-size: {TYPE['body']}px;
        selection-background-color: {t['primary']};
        selection-color: {t['onPrimary']};
    }}
    QLineEdit:hover  {{ background: {t['surfaceContainerHighest']}; }}
    QLineEdit:focus  {{ border: 1px solid {t['primary']}; }}

    QPushButton {{
        background: {t['surfaceContainerHigh']}; color: {t['onSurface']};
        border: none;
        border-radius: {RAD['md']}px;
        padding: 0 {SP['xs']}px;
        font-weight: 600; font-size: {TYPE['body']}px;
    }}
    QPushButton:hover    {{ background: {t['surfaceContainerHighest']}; }}
    QPushButton:pressed  {{ background: {t['outlineVariant']}; }}
    /* 禁用态不能和卡片底色同色（surfaceContainerLow）：那样按钮块面会整块消失，
       三个按钮平分整行后只剩中间的文字浮着，看起来像右侧一大片留白。 */
    QPushButton:disabled {{ background: {t['surfaceContainer']};
                            color: {t['outline']}; }}

    QPushButton#hero {{
        background: {t['primary']}; color: {t['onPrimary']}; border: none;
    }}
    QPushButton#hero:hover    {{ background: {t['primaryHover']}; }}
    QPushButton#hero:pressed  {{ background: {t['primaryPressed']}; }}

    /* 次级工具按钮：透明底 + 小字，只靠文字与悬停变色表达可点。
       和主操作（实心块）拉开权重差，一行两个也不会在窄窗口里抢视线。 */
    QPushButton#tool {{
        background: transparent; color: {t['onSurfaceVariant']};
        padding: 0 {SP['xs']}px;
        font-size: {TYPE['caption']}px; font-weight: 400;
    }}
    QPushButton#tool:hover   {{ color: {t['primary']}; }}
    QPushButton#tool:pressed {{ color: {t['primaryPressed']}; }}
    QPushButton#tool:disabled {{ background: transparent; color: {t['outline']}; }}

    /* 抽屉标题：整行可点，看起来像分组小标题而不是按钮 */
    QPushButton#drawer {{
        background: transparent; color: {t['primary']};
        text-align: left; padding: 0;
        font-size: {TYPE['caption']}px; font-weight: 600;
    }}
    QPushButton#drawer:hover   {{ color: {t['primaryHover']}; }}
    QPushButton#drawer:checked {{ color: {t['primary']}; }}

    QPushButton#danger {{
        background: {t['errorContainer']}; color: {t['onErrorContainer']};
        border: none;
    }}
    QPushButton#danger:hover    {{ background: {t['error']};
                                    color: {t['onError']}; }}
    QPushButton#danger:disabled {{ background: {t['surfaceContainer']};
                                   color: {t['outline']}; }}

    QProgressBar {{
        background: {t['surfaceContainerHighest']};
        border: none; border-radius: {RAD['sm']}px;
    }}
    QProgressBar::chunk {{
        background: {t['primary']}; border-radius: {RAD['sm']}px;
    }}

    QTextEdit {{
        background: {t['surfaceContainerLowest']};
        border: none;
        border-radius: {RAD['lg']}px;
        padding: {SP['sm']}px {SP['md']}px;
        font-family: {FONT_MONO};
        font-size: {TYPE['caption']}px;
        color: {t['onSurface']};
    }}

    QScrollBar:vertical {{
        background: transparent; width: {SP['sm']}px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {t['outlineVariant']}; border-radius: {RAD['sm']}px;
        min-height: {SP['xl']}px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {t['outline']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QMenu {{
        background: {t['surfaceContainerHigh']};
        border: none; border-radius: {RAD['md']}px;
        padding: {SP['xxs']}px;
        color: {t['onSurface']};
    }}
    QMenu::item {{
        padding: {SP['xs']}px {SP['md']}px;
        border-radius: {RAD['sm']}px;
    }}
    QMenu::item:selected {{ background: {t['primaryContainer']};
                            color: {t['onPrimaryContainer']}; }}

    QMessageBox {{ background: {t['surfaceContainer']}; }}
    QMessageBox QLabel {{ color: {t['onSurface']}; }}
    QToolTip {{
        background: {t['surfaceContainerHighest']}; color: {t['onSurface']};
        border: none; padding: {SP['xxs']}px {SP['xs']}px;
    }}
    """
