<#
capture_popup_info.ps1
Diagnostic helper - NOT part of the automated test flow.

Run this from your own interactive PowerShell session (must be the same desktop session
that PassMark is running in) the moment you see an unexpected popup (e.g. the OpenCL error
during Graphics Mark) BEFORE clicking OK. It dumps every top-level window belonging to
PerformanceTest64.exe, plus all child controls of any dialog-class (#32770) windows, to both
the console and a timestamped text file - so we can see the popup's exact title, class, and
button labels and build a precise auto-dismiss rule instead of guessing.

Usage:
    .\capture_popup_info.ps1
#>

Add-Type -Namespace Native -Name PM -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);
[DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc enumProc, IntPtr lParam);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
[DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder text, int count);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
[DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr hWnd);
public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
'@

function Get-AllTopWindows {
    $list = @()
    $cb = {
        param($h, $l)
        if ([Native.PM]::IsWindowVisible($h)) {
            $sbT = New-Object System.Text.StringBuilder 256
            [Native.PM]::GetWindowText($h, $sbT, 256) | Out-Null
            $sbC = New-Object System.Text.StringBuilder 256
            [Native.PM]::GetClassName($h, $sbC, 256) | Out-Null
            $procId = 0
            [Native.PM]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
            $script:__list += [PSCustomObject]@{H=$h; PID=$procId; Class=$sbC.ToString(); Title=$sbT.ToString()}
        }
        return $true
    }
    $script:__list = @()
    [Native.PM]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    return $script:__list
}

function Get-ChildControls2($parentHwnd) {
    $script:__ctrls = @()
    $cb2 = {
        param($h, $l)
        $sbT = New-Object System.Text.StringBuilder 256
        [Native.PM]::GetWindowText($h, $sbT, 256) | Out-Null
        $sbC = New-Object System.Text.StringBuilder 256
        [Native.PM]::GetClassName($h, $sbC, 256) | Out-Null
        $id = [Native.PM]::GetDlgCtrlID($h)
        $script:__ctrls += [PSCustomObject]@{H=$h; Class=$sbC.ToString(); Id=$id; Text=$sbT.ToString()}
        return $true
    }
    [Native.PM]::EnumChildWindows($parentHwnd, $cb2, [IntPtr]::Zero) | Out-Null
    return $script:__ctrls
}

$pm = Get-Process PerformanceTest64 -ErrorAction SilentlyContinue
if (-not $pm) { Write-Host "PerformanceTest64 is not running." -ForegroundColor Red; exit 1 }

$out = New-Object System.Collections.Generic.List[string]
$out.Add("=== Popup capture @ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===")

$all = Get-AllTopWindows | Where-Object { $_.PID -eq $pm.Id }
foreach ($w in $all) {
    $line = "WINDOW: hwnd=$($w.H) class='$($w.Class)' title='$($w.Title)'"
    $out.Add($line)
    if ($w.Class -eq "#32770") {
        $ctrls = Get-ChildControls2 $w.H
        foreach ($c in $ctrls) {
            $out.Add("    CONTROL: id=$($c.Id) class='$($c.Class)' text='$($c.Text)'")
        }
    }
}

$out | ForEach-Object { Write-Host $_ }
$file = "popup_capture_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
$out | Out-File -FilePath $file -Encoding utf8
Write-Host "`nSaved to: $file" -ForegroundColor Green
