@echo off
chcp 65001 >nul
echo 正在安装依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo 安装失败，请确认已安装 Python 并加入 PATH。
) else (
  echo 完成！运行: python main.py
)
pause
