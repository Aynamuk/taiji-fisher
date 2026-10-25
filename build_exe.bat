@echo off
rem 打包单文件 exe（窗口版，双击自动请求管理员权限）
rem 产物在 dist\TaijiFisher.exe，可自由改名
cd /d %~dp0
python -m PyInstaller --noconfirm --clean TaijiFisher.spec
echo.
echo 完成: dist\TaijiFisher.exe
pause
