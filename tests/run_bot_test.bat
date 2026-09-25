@echo off
rem 整链路测试：启动 bot 跑 1 个周期（限速 12s），输出写 tests\bot.out
rem 需要管理员权限（WinDivert 驱动加载）
cd /d "%~dp0.."
python main.py --cli --keywords fishfake --cast-key scrolllock --rate-kb 1 --throttle 12 --release 2 --cycles 1 --interval 0.8 > tests\bot.out 2>&1
exit /b %errorlevel%
