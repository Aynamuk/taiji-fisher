# 清理残留进程与 PyInstaller 临时目录
#
# 用法：在项目根目录执行  powershell -File tests\kill_all.ps1
#
# 注意：原版硬编码了本机 PID（5632/24432/...）与固定用户名路径，
# 换机器就失效且泄露本机信息。改为按进程名匹配 + 用 $env:TEMP。

Write-Host '--- 结束太极炸鱼助手相关进程 ---'
Get-Process |
    Where-Object { $_.ProcessName -match '太极|TaijiFisher' } |
    ForEach-Object {
        Write-Host ('KILL: ' + $_.Id + ' ' + $_.ProcessName)
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 1

$still = Get-Process | Where-Object { $_.ProcessName -match '太极|TaijiFisher' }
if ($still) {
    $still | ForEach-Object { Write-Host ('STILL: ' + $_.Id) }
} else {
    Write-Host '没有残留进程'
}

Write-Host '--- 清理 PyInstaller 解包临时目录 ---'
Get-ChildItem $env:TEMP -Directory -Filter '_MEI*' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host 'KILL_DONE'
