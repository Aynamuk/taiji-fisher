Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class M { [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y); [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, UIntPtr i); }'
[M]::SetCursorPos(186, 495) | Out-Null
Start-Sleep -Milliseconds 300
[M]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[M]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
Write-Host CLICKED
