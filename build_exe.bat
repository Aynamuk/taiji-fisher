@echo off
rem 打包单文件 exe（窗口版，双击自动请求管理员权限）
rem 产物在 dist\TaijiFisher.exe，可自由改名
cd /d %~dp0
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
  --name "TaijiFisher" ^
  --collect-all customtkinter ^
  --collect-all pystray ^
  --add-binary "vendored\tjnet.dll;vendored" ^
  --add-binary "vendored\tjnet.sys;vendored" ^
  main.py
echo.
echo 完成: dist\TaijiFisher.exe
pause
