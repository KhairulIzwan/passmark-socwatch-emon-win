<#
.SYNOPSIS
 Read-only probe: dumps PassMark's menu tree (WM_COMMAND ids + captions) so the Cmd* parameters
 of run_passmark_auto.ps1 / run_combined_test.ps1 can be verified for a given PassMark version.

.DESCRIPTION
 Run from an interactive PowerShell window (not session 0). Launches PassMark if not running.
 Sends no commands - it only reads menu data.
#>
param([string]$PassMarkExe = "C:\Program Files\PerformanceTest\PerformanceTest64.exe")

Add-Type -Namespace N -Name P -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc f, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern IntPtr GetMenu(IntPtr h);
[DllImport("user32.dll")] public static extern int GetMenuItemCount(IntPtr m);
[DllImport("user32.dll")] public static extern IntPtr GetSubMenu(IntPtr m, int i);
[DllImport("user32.dll")] public static extern uint GetMenuItemID(IntPtr m, int i);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetMenuString(IntPtr m, uint id, System.Text.StringBuilder s, int n, uint flags);
'@

$pm = Get-Process PerformanceTest64 -ErrorAction SilentlyContinue
if (-not $pm) {
    Start-Process $PassMarkExe -WorkingDirectory (Split-Path $PassMarkExe)
    Start-Sleep 20
    $pm = Get-Process PerformanceTest64
}

$script:main = [IntPtr]::Zero
$script:all = @()
for ($try = 0; $try -lt 30 -and $script:main -eq [IntPtr]::Zero; $try++) {
    $script:all = @()
    $cb = [N.P+EnumWindowsProc]{ param($h, $l)
        $p = 0; [N.P]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
        if ($p -eq $pm.Id -and [N.P]::IsWindowVisible($h)) {
            $c = New-Object Text.StringBuilder 256
            $t = New-Object Text.StringBuilder 256
            [N.P]::GetClassName($h, $c, 256) | Out-Null
            [N.P]::GetWindowText($h, $t, 256) | Out-Null
            $hasMenu = [N.P]::GetMenu($h) -ne [IntPtr]::Zero
            $script:all += [pscustomobject]@{ H = $h; Class = $c.ToString(); Title = $t.ToString(); HasMenu = $hasMenu }
        }
        $true }
    [N.P]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    $hit = $script:all | Where-Object { $_.HasMenu } | Select-Object -First 1
    if ($hit) { $script:main = $hit.H } else { Start-Sleep 1 }
}
"Visible windows of PID $($pm.Id):"
$script:all | Format-Table Class, Title, HasMenu -AutoSize | Out-String
if ($script:main -eq [IntPtr]::Zero) { throw "No visible PassMark window with a menu found - are you in an interactive session?" }

function Dump($m, $indent) {
    $n = [N.P]::GetMenuItemCount($m)
    for ($i = 0; $i -lt $n; $i++) {
        $s = New-Object Text.StringBuilder 256
        [N.P]::GetMenuString($m, $i, $s, 256, 0x400) | Out-Null
        $sub = [N.P]::GetSubMenu($m, $i)
        $id = [N.P]::GetMenuItemID($m, $i)
        "$indent[$i] id=$id '$($s.ToString())'"
        if ($sub -ne [IntPtr]::Zero) { Dump $sub ($indent + "    ") }
    }
}
Dump ([N.P]::GetMenu($script:main)) ""
