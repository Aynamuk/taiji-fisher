@echo off 
cd /d C:\Users\Administrator\.zcode\workspace\default\taiji-fisher 
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe main.py --cli --keywords fishfake --cast-key scrolllock --rate-kb 1 --throttle 12 --release 2 --cycles 1 --interval 0.8 > tests\bot.out 2>&1 
exit /b %0%
