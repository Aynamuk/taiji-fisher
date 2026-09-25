@echo off
rem 停止行为测试：--stop-min 0.2 验证「到点自动停」，输出写 tests\bot_stop.out
rem 需要管理员权限（WinDivert 驱动加载）
cd /d "%~dp0.."
python main.py --cli --keywords fishfake --cast-key scrolllock --rate-kb 1 --throttle 3 --release 2 --cycles 0 --stop-min 0.2 --interval 0.8 > tests\bot_stop.out 2>&1
exit /b %errorlevel%
