taskkill /PID 5632 /PID 24432 /PID 28072 /PID 29548 /F
Start-Sleep -Seconds 1
Get-Process | Where-Object { $_.ProcessName -match '太极|TaijiFisher' } | ForEach-Object { Write-Host ('STILL: ' + $_.Id) }
Get-ChildItem 'C:\Users\Administrator\AppData\Local\Temp' -Directory -Filter '_MEI*' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host KILL_DONE
