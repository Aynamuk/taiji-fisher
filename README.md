# 太极炸鱼助手 · 燕云十六声

利用《燕云十六声》的"太极炸鱼"技巧挂机刷鱼获的本地辅助工具。
思路参考 MAA（MaaAssistantArknights）：**定点网络整形 + 模拟按键输入 + 状态机调度**。

> ⚠️ 仅供个人学习研究使用。请自行评估账号风险，勿用于任何商业用途或分发。

## ⚠️ 风险警告（使用前必读）

本工具会做两件容易触发游戏反作弊的事：

1. **加载一个内核态网络驱动**（`vendored/WinDivert64.sys`）拦截游戏流量并限速；
2. **利用游戏的同步漏洞**，让技能 CD 从原本的 N 秒卡到 1 秒。

**网易反作弊会监控未签名内核驱动的加载**，无论目的是什么——这是高危检测项。
同时"利用漏洞加速 CD"违反《燕云十六声》用户协议，官方公告明确打击此类行为。

**真实风险 = 账号封禁**（即使工具本身能正常启动，也不代表反作弊没盯上你）。
本仓库仅提供技术研究样本，作者不对任何账号后果负责。

## 原理

炸鱼技巧：把游戏限速到 ~1KB/s，客户端与服务器的时间同步被打断，
太极技能的 CD 表现卡在 1 秒，可以连续施放炸鱼；
限速太久服务器会踢下线，所以要在踢线前解除限速让游戏恢复正常。

本工具把整个过程自动化为一个循环：

```
┌────────────────────────────────────────────────────────┐
│ 1. 扫描游戏进程(yysls)的所有 TCP/UDP 端点（每 5 秒刷新，  │
│    重连自适应）                                          │
│ 2. WinDivert 只捕获游戏连接的【下载（入站）】包，令牌桶    │
│    限速到 N KB/s；上行（施放请求/心跳）保持畅通，          │
│    服务器不踢线、施放即时生效                              │
│ 3. 限速期间每 cast_interval 秒模拟按一次技能键             │
│ 4. throttle_seconds 后解除限速，排队包以 256KB/s 回灌，    │
│    避免突发流量触发服务器断连                              │
│ 5. release_seconds 恢复期，游戏追上进度，鱼获自动进背包     │
│ 6. 回到 1，循环                                           │
└────────────────────────────────────────────────────────┘
```

关键设计：

- **定点限速**：按进程当前连接的远端端点构造 WinDivert 过滤串，
  不影响同机其他软件（Discord、浏览器等完全不受限）；
- **自适应重连**：游戏断线重连后端点变化，限速会自动跟随新端点重建过滤串；
- **安全兜底**：`F12` 任何时候一键解限并停止；进程消失/无连接时自动暂停；
  队列有上限，异常时丢包由 TCP 重传兜底。

## 安装

**方式一：直接用打包好的 exe（推荐）**

仓库已内置打包好的 `dist/TaijiFisher.exe`（单文件，约 31MB），无需 Python 环境。
在 [Releases](../../releases/tag/v1.0) 或仓库的 `dist/` 目录下载即可，双击运行；
Windows 会弹 UAC 管理员确认（exe 内嵌了管理员清单），确认后直接进 GUI。
`config.json` 会生成在 exe 旁边；WinDivert 驱动内嵌在 exe 里，运行时自动解包加载。
exe 可自由改名。注意：未签名的 PyInstaller 单文件 exe 容易被杀软误报，
报毒请加白名单或改用方式二。

**方式二：源码运行**

1. 安装 [Python 3.10 / 3.11](https://www.python.org/downloads/)（安装时勾选 Add to PATH）；
2. 双击目录下的 `安装依赖.bat`（内容就是 `pip install -r requirements.txt`），
   或手动执行 `pip install -r requirements.txt`；
3. `vendored/` 目录需要 `tjnet.dll` + `tjnet.sys`（本仓库已附带，即官方
   [WinDivert 2.2.2](https://github.com/basil00/WinDivert) x64 的
   `WinDivert.dll`/`WinDivert64.sys` 改名版——WinDivert 官方支持同名重命名，
   改名是为了避免被安全软件按文件名特征拦截；LGPL/GPL 双许可见
   `vendored/WinDivert-LICENSE`）。

## 重新打包 exe

改完代码后双击 `build_exe.bat`（内部执行 PyInstaller），产物在 `dist/TaijiFisher.exe`：

```bat
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
  --name "TaijiFisher" ^
  --add-binary "vendored\WinDivert.dll;vendored" ^
  --add-binary "vendored\WinDivert64.sys;vendored" ^
  main.py
```

`--windowed`：无黑色控制台；`--uac-admin`：双击自动请求管理员权限。
命令行模式（`--cli`）没有打进窗口版 exe，需要 CLI 时用源码运行。

## GUI 预览图约定

`docs/gui_preview.png` 是界面预览图。**每次改动 GUI 后**（源码方式）运行：

```bat
python tests/grab_gui.py
```

它会启动检测、离屏抓取当前界面并重新生成预览图（窗口被遮挡也能抓）。

## 使用

1. 启动游戏，站到水边、面向水域；
2. 双击 `dist/TaijiFisher.exe`（源码方式则 `python main.py`，会自动弹 UAC）；
3. 点"扫描游戏进程"确认找到了 yysls 客户端（看得到 TCP/UDP 端点列表）；
4. 把"技能键"改成你游戏里太极对应的按键；
5. 点 **▶ 开始 (F9)**：前台模式会自动把游戏窗口置前、助手缩进系统托盘
   （后台模式不置前，同样缩进托盘），进入 "限速炸鱼中 → 解限恢复中" 循环，
   鱼获自动进背包，人挂着就行；
6. 任务结束（停止/完成/定时到/出错）会自动从托盘恢复窗口；托盘图标
   左键恢复窗口，右键菜单可显示/停止/退出；
7. 热键：**F9** 暂停/继续，**F10** 停止，**F12** 紧急解限并停止。

命令行模式（无界面）：

```bat
python main.py --cli --cast-key r --rate-kb 1 --throttle 30 --release 10 --stop-min 60
```

## 参数怎么调

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| 限速 KB/s | 0.5 | 仅限**下载方向**。判定标准：日志"限速统计"的**队列 > 0** 才是真的在卡；实测 0.5 可用，1.0 高于游戏空闲流量会限了个寂寞 |
| 限速时长 s | 600 | 单次限速持续 10 分钟，到点自动解限恢复一轮 |
| 解限时长 s | 10 | 至少 10s，让游戏把状态追回来再进下一轮 |
| 施放间隔 s | 1.4 | 限速态 CD 卡 1 秒，间隔略大于 1 秒即可 |
| 循环次数 | 0（无限） | 想挂 X 轮就填 X |
| 定时停止(分) | 0（不停） | 挂机 N 分钟后自动解限停止，到点立即恢复网络（即使在限速期中途也会先解限） |
| 输入模式 | 前台模式（推荐） | 前台=游戏置前时用系统级注入，最稳；后台=向窗口投递消息，游戏多半不理会 |

游戏进程识别关键字固定为 `yysls`（客户端进程名），无需配置；
CLI 可用 `--keywords` 临时覆盖。

## 常见问题

**点开始就报 "WinDivertOpen 失败"**
- WinError 5：没用管理员运行；
- WinError 577：Windows"内核隔离-内存完整性"或杀软拦了驱动，
  在 Windows 安全中心 → 设备安全性 → 内核隔离里关闭"内存完整性"后重启；
- WinError 2：`vendored/` 里缺 `WinDivert64.sys`。

**游戏提示异常/被踢**：限速时长太激进，把"限速时长"调小、"解限时长"调大。

**按键没反应**：程序开始时会自动把游戏窗口置前，之后请别点别的窗口
（前台模式按键只进前台窗口）；确认"技能键"和游戏按键绑定一致。

**CD 一直卡不住 / 限速没生效？** 看日志里的"限速统计"行：
- 捕获始终为 0KB → 限速没碰到游戏服务器的连接，最常见原因是开了
  **加速器**（流量绕道加速器进程），关掉加速器再试；或扫描到的是
  别的进程，点"扫描游戏进程"核对列出的端点是否随游戏动作变化；
- 捕获有数字但 CD 不卡 → 下载限速值可能还不够低，把限速 KB/s 降到
  0.5 再试；游戏服务器连接若频繁更换端点，程序每 5 秒会自动跟随。

**限速后游戏完全卡死而不是只有 CD 卡**：说明限到了心跳也过不去，
把 KB/s 略微调大（1.5~2）。

## 项目结构

```
main.py        入口：提权、CLI/GUI 分发
gui.py         Tkinter 界面
bot.py         循环状态机（限速期/恢复期调度、端点刷新、暂停/紧急停止）
throttler.py   WinDivert 令牌桶限速器（FlowShaper）+ 会话管理
windivert.py   WinDivert 2.2 的 ctypes 封装
gameproc.py    进程识别（进程名/窗口标题）+ 网络端点扫描
gameinput.py   SendInput 前台注入 / PostMessage 后台注入
paths.py       源码/exe 双模式路径解析（config 位置、vendored 位置）
build_exe.bat  PyInstaller 打包脚本（产物 dist/TaijiFisher.exe）
docs/          gui_preview.png 界面预览图
vendored/      WinDivert 官方二进制（dll/sys/license）
tests/         本机验证脚本（限速/按键/进程/整链路/抓预览图）
```
