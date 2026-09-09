@echo off
cd /d C:\Users\Administrator\.zcode\workspace\default\taiji-fisher
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe main.py --cli --keywords fishfake --cast-key scrolllock --rate-kb 1 --throttle 3 --release 2 --cycles 0 --stop-min 0.2 --interval 0.8 > tests\bot_stop.out 2>&1
exit /b %errorlevel%
