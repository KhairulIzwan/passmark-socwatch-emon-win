<#
.SYNOPSIS
 Combined PassMark + SocWatch + EMON telemetry capture - FULLY AUTOMATED.

.DESCRIPTION
 1. Launches PassMark GUI (if not already running)
 2. Sets Preferences: Test duration + Test iterations (via Edit > Preferences automation)
 3. Triggers "Run All Tests" (same as manual "Run Benchmark" button) and confirms the Y/N prompt
 4. Starts SocWatch + EMON telemetry the instant the benchmark actually begins (no fixed duration -
    SocWatch runs under a generous safety cap and EMON loops indefinitely; both are gracefully
    stopped - SocWatch via a real Ctrl-C signal, EMON via its own documented "-stop" command -
    the moment PassMark's completion dialog is detected, so capture length always matches the
    actual workload length exactly)
 5. Detects completion via PassMark's own "benchmark complete" summary dialog (not CPU plateau)
 6. Closes the post-run "Submit Baseline" summary dialog (never touches the submit button)
 7. Auto-triggers PassMark's "Save results as text" + auto-clicks Export, with retry + freshness verification
 8. Parses PerfRes.txt and copies everything (plus a system_info.txt HW/SW config snapshot) into
    one timestamped results folder under .\Results\

 Run this from an elevated PowerShell in your own interactive session (not SYSTEM/session 0).

.PARAMETER TestDuration
 PassMark's "Test Duration" preference: Short | Medium | Long | VeryLong.

.PARAMETER TestIterations
 Number of repeats per sub-test (PassMark's "Test Iterations" preference).

.PARAMETER ConfirmBeforeRun
 If set, asks Y/N before starting the benchmark. Default is fully automatic (no prompts).

.PARAMETER SocWatchSafetyCapSeconds
 Hard safety ceiling for SocWatch only - NOT the expected run length. SocWatch is normally
 stopped early via Ctrl-C the instant the benchmark finishes; this cap only protects against a
 stuck/undetected completion. Default 900 (15 min).

.PARAMETER PowerPlan
 Power plan to use DURING the benchmark: AsIs | Balanced | HighPerformance |
 UltimatePerformance | PowerSaver. Default HighPerformance. "Balanced" (Windows default)
 throttles for power savings and can make benchmark runs inconsistent run-to-run. The
 original plan is always restored afterward, even on a mid-run error. Run with -Help to see
 the exact power plans currently available on this machine.

.PARAMETER Help
 Show this usage information (including the power plans available on this machine) and exit
 without launching anything.

.EXAMPLE
 .\run_combined_test.ps1 -TestDuration Short -TestIterations 1
.EXAMPLE
 .\run_combined_test.ps1 -TestDuration Long -TestIterations 3 -PowerPlan UltimatePerformance
.EXAMPLE
 .\run_combined_test.ps1 -Help
#>

param(
    [int]$SocWatchSafetyCapSeconds = 900, # hard ceiling only - SocWatch is stopped early via Ctrl-C as soon as the benchmark actually finishes
    [string]$TestDuration  = "Short", # Short | Medium | Long | VeryLong
    [int]$TestIterations   = 3,
    [switch]$ConfirmBeforeRun,         # if set, asks Y/N before starting the benchmark; default is fully automatic
    [ValidateSet("AsIs","Balanced","HighPerformance","UltimatePerformance","PowerSaver")]
    [string]$PowerPlan = "HighPerformance",  # power plan to use DURING the benchmark; original plan is restored afterward. "AsIs" = don't touch it.
    [switch]$Help                      # show usage (incl. available power plans on this machine) and exit
)

if ($Help) {
    Write-Host @"

Combined PassMark + SocWatch + EMON telemetry capture - FULLY AUTOMATED

USAGE:
  .\run_combined_test.ps1 [-TestDuration <Short|Medium|Long|VeryLong>] [-TestIterations <n>]
                           [-PowerPlan <AsIs|Balanced|HighPerformance|UltimatePerformance|PowerSaver>]
                           [-SocWatchSafetyCapSeconds <n>] [-ConfirmBeforeRun] [-Help]

PARAMETERS:
  -TestDuration             Short | Medium | Long | VeryLong   (default: Short)
  -TestIterations           Number of repeats per sub-test     (default: 3)
  -PowerPlan                Power plan used during the run - original is always restored after
                             (default: HighPerformance)
  -SocWatchSafetyCapSeconds Safety ceiling only, not the expected run length (default: 900)
  -ConfirmBeforeRun         Ask Y/N before starting the benchmark (default: fully automatic)
  -Help                     Show this help and exit

EXAMPLES:
  .\run_combined_test.ps1 -TestDuration Short -TestIterations 1
  .\run_combined_test.ps1 -TestDuration Long -TestIterations 3 -PowerPlan UltimatePerformance
  .\run_combined_test.ps1 -ConfirmBeforeRun

Full details: Get-Help .\run_combined_test.ps1 -Full   (or see README.md)
"@ -ForegroundColor Cyan

    Write-Host "POWER PLANS AVAILABLE ON THIS MACHINE:" -ForegroundColor Cyan
    powercfg /list
    exit 0
}

$ErrorActionPreference = "Stop"
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$resultsDir = Join-Path $PSScriptRoot "Results\$ts"
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null
Write-Host "Results will be saved to: $resultsDir" -ForegroundColor Cyan

# ---------- Power plan handling ----------
# "Balanced" (Windows default) throttles for power savings and can make benchmark runs
# inconsistent run-to-run. We record the original plan, optionally switch to a steadier one for
# the duration of the run (user-selectable via -PowerPlan), and always restore the original plan
# afterward (even if PowerPlan is "AsIs", so a manual power-plan change by a prior run never
# leaks into this one's "original plan" baseline - we just don't switch away from it).
$PowerPlanGuids = @{
    "Balanced"            = "381b4222-f694-41f0-9685-ff5bb260df2e"
    "HighPerformance"     = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
    "PowerSaver"          = "a1841308-3541-4fab-bc81-f71556f20b4a"
    "UltimatePerformance" = "e9a42b02-d5df-448d-aa00-03f14749eb61"  # hidden scheme; enabled via -duplicatescheme if not already present
}

function Get-ActivePowerSchemeInfo {
    $line = (powercfg /getactivescheme) -join "`n"
    if ($line -match "Power Scheme GUID:\s*([0-9a-fA-F-]+)\s*\(([^)]+)\)") {
        return [PSCustomObject]@{ Guid = $Matches[1]; Name = $Matches[2] }
    }
    return $null
}

$originalScheme = Get-ActivePowerSchemeInfo
$appliedPowerPlanName = "AsIs (left unchanged)"
if ($PowerPlan -ne "AsIs" -and $originalScheme) {
    try {
        $targetGuid = $PowerPlanGuids[$PowerPlan]
        if ($PowerPlan -eq "UltimatePerformance") {
            $listOut = (powercfg /list) -join "`n"
            if ($listOut -notmatch [regex]::Escape($targetGuid)) {
                powercfg -duplicatescheme $targetGuid | Out-Null   # exposes the normally-hidden Ultimate Performance scheme
            }
        }
        powercfg /setactive $targetGuid
        $appliedPowerPlanName = $PowerPlan
        Write-Host "Power plan: $($originalScheme.Name) -> $PowerPlan (will restore '$($originalScheme.Name)' when done)" -ForegroundColor Cyan
    } catch {
        Write-Host "  [WARN] Could not switch power plan to $PowerPlan - continuing on current plan ($($originalScheme.Name)). Error: $_" -ForegroundColor Red
        $appliedPowerPlanName = "$($originalScheme.Name) (switch failed, left unchanged)"
    }
} elseif ($originalScheme) {
    Write-Host "Power plan: left as-is ($($originalScheme.Name))" -ForegroundColor Cyan
}

# ---------- Capture HW/SW test-bed configuration alongside the results ----------
function Write-SystemInfo($path, $powerPlanNote) {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $ram = Get-CimInstance Win32_PhysicalMemory
    $bios = Get-CimInstance Win32_BIOS
    $os = Get-CimInstance Win32_OperatingSystem
    $gpus = Get-CimInstance Win32_VideoController

    $lines = @()
    $lines += "=== Test-bed configuration ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) ==="
    $lines += ""
    $lines += "-- CPU --"
    $lines += "Model: $($cpu.Name)"
    $lines += "Cores/Threads: $($cpu.NumberOfCores) cores / $($cpu.NumberOfLogicalProcessors) threads"
    $lines += "Max clock speed (reported): $($cpu.MaxClockSpeed) MHz"
    $lines += ""
    $lines += "-- Memory --"
    $totalGB = [math]::Round(($ram | Measure-Object Capacity -Sum).Sum / 1GB, 1)
    $lines += "Total installed: $totalGB GB across $($ram.Count) module(s)"
    foreach ($m in $ram) {
        $lines += "  - $([math]::Round($m.Capacity/1GB,1)) GB @ $($m.Speed) MT/s, $($m.Manufacturer) $($m.PartNumber)".Trim()
    }
    $lines += ""
    $lines += "-- BIOS --"
    $lines += "Version: $($bios.SMBIOSBIOSVersion)  |  Manufacturer: $($bios.Manufacturer)  |  Release date: $($bios.ReleaseDate)"
    $lines += ""
    $lines += "-- Operating System --"
    $lines += "$($os.Caption) (Build $($os.BuildNumber), $($os.OSArchitecture))"
    $lines += ""
    $lines += "-- GPU(s) --"
    foreach ($g in $gpus) { $lines += "$($g.Name) - driver $($g.DriverVersion) ($($g.DriverDate))" }
    $lines += ""
    $lines += "-- Power plan --"
    $lines += $powerPlanNote
    $lines | Out-File -FilePath $path -Encoding utf8
}
Write-SystemInfo (Join-Path $resultsDir "system_info.txt") "Original plan: $($originalScheme.Name) | Applied for this run: $appliedPowerPlanName"

# Safety net: restore the original power plan even if the script aborts with an error partway
# through (the normal end-of-script restore further below only runs on a clean finish).
$script:powerPlanRestored = $false
function Restore-OriginalPowerPlanOnce {
    if ($script:powerPlanRestored) { return }
    if ($PowerPlan -ne "AsIs" -and $originalScheme -and $appliedPowerPlanName -eq $PowerPlan) {
        try {
            powercfg /setactive $originalScheme.Guid
            Write-Host "Power plan restored to: $($originalScheme.Name)" -ForegroundColor Cyan
        } catch {
            Write-Host "  [WARN] Could not restore original power plan ($($originalScheme.Name)). Please set it back manually. Error: $_" -ForegroundColor Red
        }
    }
    $script:powerPlanRestored = $true
}
trap {
    Write-Host "`n[ERROR] Script aborting due to an unhandled error - restoring power plan before exit." -ForegroundColor Red
    Restore-OriginalPowerPlanOnce
}

# ---------- Native API helpers for PassMark automation ----------
Add-Type -Namespace Native -Name Combined -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
[DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc lpEnumFunc, IntPtr lParam);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
[DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
[DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
[DllImport("user32.dll", EntryPoint="SendMessageW", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessageStr(IntPtr hWnd, uint Msg, IntPtr wParam, string lParam);
public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
'@

# Sends a graceful Ctrl-C to a specific child console process (NOT a kill) - this is the
# documented, safe way to stop EMON/SocWatch early ("Use Ctrl-C to stop collection").
# IMPORTANT: this is done by spawning a tiny, separate, disposable helper powershell.exe process
# that does the FreeConsole/AttachConsole(target)/GenerateConsoleCtrlEvent dance and then exits.
# Earlier versions did this self-console-swap trick INSIDE our own long-lived interactive
# PowerShell process, which corrupted its console handles and crashed/closed the whole window
# after the 2nd call. A short-lived throwaway child process cannot ever affect our own console.
function Send-GracefulCtrlC($targetProcId) {
    # Single-quoted here-string = zero interpolation, so every $ below is 100% literal in the
    # generated helper script. The only substitution is the plain textual PID placeholder.
    $helperTemplate = @'
Add-Type -Namespace H -Name C -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern bool FreeConsole();
[DllImport("kernel32.dll")] public static extern bool AttachConsole(uint dwProcessId);
[DllImport("kernel32.dll")] public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
[DllImport("kernel32.dll")] public static extern bool SetConsoleCtrlHandler(IntPtr HandlerRoutine, bool Add);
"@
[H.C]::SetConsoleCtrlHandler([IntPtr]::Zero, $true) | Out-Null
[H.C]::FreeConsole() | Out-Null
$ok = [H.C]::AttachConsole(__TARGETPID__)
if ($ok) {
    [H.C]::GenerateConsoleCtrlEvent(0, 0) | Out-Null
    Start-Sleep -Milliseconds 500
}
exit $(if ($ok) { 0 } else { 1 })
'@
    $helperScript = $helperTemplate.Replace('__TARGETPID__', [string]$targetProcId)
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($helperScript))
    $helperProc = Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", $encoded `
        -PassThru -Wait
    return ($helperProc.ExitCode -eq 0)
}

function Get-VisibleWindowsForPid($targetPid) {
    $script:__winList = @()
    $cb = {
        param($h, $l)
        if ([Native.Combined]::IsWindowVisible($h)) {
            $p = 0
            [Native.Combined]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
            if ($p -eq $targetPid) {
                $sbT = New-Object System.Text.StringBuilder 256
                [Native.Combined]::GetWindowText($h, $sbT, 256) | Out-Null
                $sbC = New-Object System.Text.StringBuilder 256
                [Native.Combined]::GetClassName($h, $sbC, 256) | Out-Null
                $script:__winList += [PSCustomObject]@{H=$h; Class=$sbC.ToString(); Title=$sbT.ToString()}
            }
        }
        return $true
    }
    [Native.Combined]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
    return $script:__winList
}

function Get-ChildControls($parentHwnd) {
    $script:__ctrls = @()
    $cb2 = {
        param($h, $l)
        $sbT = New-Object System.Text.StringBuilder 256
        [Native.Combined]::GetWindowText($h, $sbT, 256) | Out-Null
        $sbC = New-Object System.Text.StringBuilder 256
        [Native.Combined]::GetClassName($h, $sbC, 256) | Out-Null
        $id = [Native.Combined]::GetDlgCtrlID($h)
        $script:__ctrls += [PSCustomObject]@{H=$h; Class=$sbC.ToString(); Id=$id; Text=$sbT.ToString()}
        return $true
    }
    [Native.Combined]::EnumChildWindows($parentHwnd, $cb2, [IntPtr]::Zero) | Out-Null
    return $script:__ctrls
}

function Wait-ForDialog($targetPid, $titlePattern, $timeoutMs) {
    $elapsed = 0
    while ($elapsed -lt $timeoutMs) {
        Start-Sleep -Milliseconds 100
        $elapsed += 100
        $wins = Get-VisibleWindowsForPid $targetPid
        $hit = $wins | Where-Object { $_.Title -match $titlePattern }
        if ($hit) { return $hit[0].H }
    }
    return [IntPtr]::Zero
}

# Auto-dismisses PassMark's cold-start "Warning" popup (e.g. "system not ready - checking...")
# by clicking its OK button, so no manual interaction is ever needed. Only touches dialogs whose
# title contains "Warning" - never the Run-All-Tests confirm or Submit-Baseline dialogs, which are
# handled explicitly elsewhere by exact title/control-id match.
function Close-WarningPopups($targetPid) {
    $closed = 0
    $wins = Get-VisibleWindowsForPid $targetPid
    $warnDlgs = $wins | Where-Object { $_.Title -match "Warning" }
    foreach ($wd in $warnDlgs) {
        $wCtrls = Get-ChildControls $wd.H
        $okB = $wCtrls | Where-Object { $_.Text -eq "OK" } | Select-Object -First 1
        if ($okB) {
            [Native.Combined]::PostMessage($okB.H, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # BM_CLICK
            $closed++
        } else {
            [Native.Combined]::PostMessage($wd.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # WM_CLOSE fallback
            $closed++
        }
    }
    return $closed
}

# ---------- Step 1: launch PassMark GUI ----------
$knownTestClasses = @("TestWindow","DirectWriteTest","D2DDemoApp","D3DProxyWindow","D3D Window","Direct3DWindowClass")
Write-Host "`n[1/7] Launching PassMark GUI..." -ForegroundColor Yellow
$pm = Get-Process PerformanceTest64 -ErrorAction SilentlyContinue
$coldLaunch = $false
if (-not $pm) {
    $coldLaunch = $true
    Start-Process -FilePath "C:\Program Files\PerformanceTest\PerformanceTest64.exe" -WorkingDirectory "C:\Program Files\PerformanceTest"
    Write-Host "  Cold launch detected - waiting for first-time initialization/system check (up to 60s)..."
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        $pm = Get-Process PerformanceTest64 -ErrorAction SilentlyContinue
        if ($pm) {
            $dismissed = Close-WarningPopups $pm.Id
            if ($dismissed -gt 0) { Write-Host "  [DEBUG] Auto-dismissed $dismissed cold-start Warning popup(s)." }
            break
        }
    }
}
if (-not $pm) { throw "PassMark did not launch." }

# ---------- Step 1a: resolve the REAL main app window (class "PT"), not just Process.MainWindowHandle ----------
$hwnd = [IntPtr]::Zero
for ($try = 0; $try -lt 10; $try++) {
    $wins = Get-VisibleWindowsForPid $pm.Id
    $main = $wins | Where-Object { $_.Class -eq "PT" } | Select-Object -First 1
    if ($main) { $hwnd = $main.H; break }
    Start-Sleep -Milliseconds 300
}
if ($hwnd -eq [IntPtr]::Zero) { throw "Could not find PassMark main window (class 'PT')." }
Write-Host "  PassMark PID=$($pm.Id)  MainWindowHandle=$hwnd"

# ---------- Step 1b: clean up stale leftovers from prior/interrupted runs ----------
$staleClosed = 0
for ($pass = 0; $pass -lt 5; $pass++) {
    $wins = Get-VisibleWindowsForPid $pm.Id
    $stale = $wins | Where-Object { ($_.Class -eq "#32770" -and $_.Title -eq "") -or ($_.Class -in $knownTestClasses) }
    if (-not $stale) { break }
    foreach ($s in $stale) {
        [Native.Combined]::PostMessage($s.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
        $staleClosed++
    }
    Start-Sleep -Milliseconds 500
}
if ($staleClosed -gt 0) { Write-Host "  [DEBUG] Cleaned up $staleClosed stale leftover dialog(s) before starting." -ForegroundColor Yellow }

# ---------- Step 2: set Preferences (Test duration / Test iterations) ----------
Write-Host "`n[2/7] Setting Preferences: duration=$TestDuration, iterations=$TestIterations..." -ForegroundColor Yellow
# On a cold launch, PassMark's window can exist (and even respond to class/title queries) before
# it's actually ready to process menu commands (first-run hardware scan, etc). Rather than guess a
# fixed delay, retry opening the dialog for up to ~45s and only fail if it truly never appears.
$prefDlg = [IntPtr]::Zero
$prefAttempts = if ($coldLaunch) { 15 } else { 3 }
for ($a = 1; $a -le $prefAttempts; $a++) {
    $dismissed = Close-WarningPopups $pm.Id
    if ($dismissed -gt 0) { Write-Host "  [DEBUG] Auto-dismissed $dismissed Warning popup(s)."; Start-Sleep -Milliseconds 300 }
    [Native.Combined]::SetForegroundWindow($hwnd) | Out-Null
    Start-Sleep -Milliseconds 300
    [Native.Combined]::PostMessage($hwnd, 0x0111, [IntPtr]40040, [IntPtr]::Zero) | Out-Null  # Edit > Preferences...
    $prefDlg = Wait-ForDialog $pm.Id "^Edit Preferences$" 3000
    if ($prefDlg -ne [IntPtr]::Zero) { break }
    Write-Host "  [DEBUG] Preferences dialog not up yet (attempt $a/$prefAttempts) - app may still be initializing, retrying..."
}
if ($prefDlg -eq [IntPtr]::Zero) { throw "Preferences dialog did not appear after $prefAttempts attempts." }

$ctrls = Get-ChildControls $prefDlg
$durationCombo = ($ctrls | Where-Object { $_.Id -eq 1009 })[0].H
$iterEdit      = ($ctrls | Where-Object { $_.Id -eq 1333 })[0].H
$okBtn         = ($ctrls | Where-Object { $_.Id -eq 1 })[0].H

$sel = [Native.Combined]::SendMessageStr($durationCombo, 0x014D, [IntPtr](-1), $TestDuration)  # CB_SELECTSTRING
if ($sel.ToInt32() -lt 0) { Write-Host "  WARNING: duration '$TestDuration' not found in dropdown." -ForegroundColor Red }
[Native.Combined]::SendMessageStr($iterEdit, 0x000C, [IntPtr]::Zero, "$TestIterations") | Out-Null  # WM_SETTEXT
Start-Sleep -Milliseconds 300
[Native.Combined]::PostMessage($okBtn, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # BM_CLICK OK (PostMessage: non-blocking)
Start-Sleep -Milliseconds 500
Write-Host "  Preferences applied."

# ---------- Step 3: trigger the benchmark run (telemetry starts right after this, once it's truly begun) ----------
Write-Host "`n[3/7] Triggering 'Run All Tests' (same as clicking 'Run Benchmark')..." -ForegroundColor Yellow
[Native.Combined]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 300
$postOk = [Native.Combined]::PostMessage($hwnd, 0x0111, [IntPtr]40079, [IntPtr]::Zero)  # Tests > Run All Tests
Write-Host "  [DEBUG] PostMessage(WM_COMMAND, 40079) result: $postOk"

$confirmDlg = Wait-ForDialog $pm.Id "^Run all benchmark tests\?$" 5000
if ($confirmDlg -eq [IntPtr]::Zero) {
    throw "Confirmation dialog ('Run all benchmark tests?') did not appear - aborting, nothing was started."
}
Write-Host "  [DEBUG] Confirmation dialog found: $confirmDlg" -ForegroundColor Cyan

$confirmCtrls = Get-ChildControls $confirmDlg
$yesBtn = ($confirmCtrls | Where-Object { $_.Id -eq 6 })[0].H
$noBtn  = ($confirmCtrls | Where-Object { $_.Id -eq 7 })[0].H

$answer = if ($ConfirmBeforeRun) { Read-Host "  PassMark is asking: 'You are about to run all tests, this may take several minutes...' Proceed? (Y/N)" } else { "y" }
if (-not $ConfirmBeforeRun) { Write-Host "  PassMark confirmation dialog detected - auto-confirming (pass -ConfirmBeforeRun to be asked instead)." }
if ($answer -notmatch '^(y|yes)$') {
    Write-Host "  User chose NO - clicking No and stopping the script. No telemetry was started." -ForegroundColor Red
    [Native.Combined]::PostMessage($noBtn, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # PostMessage: non-blocking
    exit 0
}
Write-Host "  Clicking Yes..." -ForegroundColor Green
[Native.Combined]::PostMessage($yesBtn, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # PostMessage: non-blocking

for ($w = 0; $w -lt 50; $w++) {
    Start-Sleep -Milliseconds 200
    $stillThere = (Get-VisibleWindowsForPid $pm.Id) | Where-Object { $_.Title -eq "Run all benchmark tests?" }
    if (-not $stillThere) { break }
}
Write-Host "  Benchmark started."

# ---------- Step 4: start telemetry NOW, right as the real workload begins - no fixed duration ----------
# EMON: "-nb" launches it non-blocking/detached (returns control immediately, confirmed ~2s) while
# it keeps sampling in the background ("-l 0" = loop forever, 1-second samples) until stopped via
# the official "emon -stop" command - this matches Intel's own reference automation pattern and is
# simpler/safer than a Ctrl-C hack (verified: -nb + -stop produces clean multi-sample CSV output).
# SocWatch: "-t $SocWatchSafetyCapSeconds" is only a safety ceiling; SocWatch has no equivalent
# detached+stop command for our GUI-driven (non -p-launchable) workload, so it is still stopped via
# a real Ctrl-C signal the instant PassMark's completion dialog is detected (confirmed graceful:
# "Use Ctrl-C to stop collection", verified clean output on a live test). Feature set below matches
# the organization's reference SocWatch/EMON automation profile (14 telemetry channels).
Write-Host "`n[4/7] Starting EMON + SocWatch telemetry (will run exactly as long as the benchmark does)..." -ForegroundColor Yellow

$emonCsv = Join-Path $resultsDir "emon.csv"
$emonArgs = '/c call "C:\Program Files (x86)\IntelSWTools\emon\sep_vars.cmd" noshell && emon -nb -C "INST_RETIRED.ANY, CPU_CLK_UNHALTED.REF_TSC, LONGEST_LAT_CACHE.MISS" -t1 -l0 -f "' + $emonCsv + '"'
$emonProc = Start-Process -FilePath "cmd.exe" -ArgumentList $emonArgs -WorkingDirectory "C:\Program Files (x86)\IntelSWTools\emon" -PassThru -WindowStyle Minimized
$emonProc.WaitForExit(15000) | Out-Null   # -nb returns control quickly once the background collector is launched

$socDir = Join-Path $resultsDir "socwatch"
$socFeatures = @("cpu-wakeup","sys-memory","cpu-freq","uncore-freq","cpu-ipc","cache","os-cpu-pstate","hw-cpu-pstate","pkg-pwr","cpu-pstate","gfx-pstate","sa-freq","pwr-limits","cpu-cstate")
$socArgs = @()
foreach ($feat in $socFeatures) { $socArgs += "-f"; $socArgs += $feat }
$socArgs += @("-o",$socDir,"-t",$SocWatchSafetyCapSeconds)
$socProc = Start-Process -FilePath "C:\Program Files\SocWatch\socwatch.exe" -ArgumentList $socArgs -WorkingDirectory "C:\Program Files\SocWatch" -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 2
$emonRunning = Get-Process -Name "emon" -ErrorAction SilentlyContinue
Write-Host "  EMON PID=$(if($emonRunning){$emonRunning.Id}else{'(not detected)'})  SocWatch PID=$($socProc.Id)"
Write-Host "  Monitoring CPU usage + active sub-test to auto-detect completion..."

# ---------- Step 5: detect completion via the REAL "benchmark complete" summary dialog ----------
# CPU-plateau alone is unreliable: Memory/Disk sub-tests are I/O-bound, not CPU-bound, so CPU can
# look "flat" while those tests are still actively running. The summary dialog (blank-title #32770
# containing a "Submit Baseline to Passmark" button, id=12104) is PassMark's own definitive signal
# that ALL sub-tests (CPU/2D/3D/Memory/Disk) have truly finished - poll for that instead.
$prevCpu = -1
$maxIters = [math]::Max([math]::Ceiling($SocWatchSafetyCapSeconds / 10) + 24, 180)
$reallyDone = $false
for ($i = 0; $i -lt $maxIters; $i++) {
    Start-Sleep -Seconds 10
    $p = Get-Process -Id $pm.Id -ErrorAction SilentlyContinue
    if (-not $p) { Write-Host "  PassMark process exited."; break }
    $cpu = [math]::Round($p.CPU, 1)
    $delta = if ($prevCpu -lt 0) { $cpu } else { [math]::Round($cpu - $prevCpu, 1) }

    $wins = Get-VisibleWindowsForPid $pm.Id
    $activeTest = $wins | Where-Object { $_.Class -in $knownTestClasses -and $_.Title -ne "" } | Select-Object -First 1
    $activeTestLabel = if ($activeTest) { $activeTest.Title } else { "(CPU/Memory/Disk test - no graphics window / between sub-tests)" }

    $blankDlgs = $wins | Where-Object { $_.Class -eq "#32770" -and $_.Title -eq "" }
    foreach ($bd in $blankDlgs) {
        $bdCtrls = Get-ChildControls $bd.H
        if ($bdCtrls | Where-Object { $_.Id -eq 12104 }) { $reallyDone = $true; break }
    }

    Write-Host "  t=$(($i+1)*10)s CPU=$cpu delta=$delta running: $activeTestLabel$(if($reallyDone){' [COMPLETE DIALOG DETECTED]'})"
    $prevCpu = $cpu
    if ($reallyDone) { Write-Host "  Benchmark-complete summary dialog confirmed -> all sub-tests (CPU/2D/3D/Memory/Disk) finished." -ForegroundColor Green; break }
}
if (-not $reallyDone) { Write-Host "  [WARN] Safety timeout reached without seeing the completion dialog - proceeding anyway, results may be incomplete." -ForegroundColor Red }

# ---------- Step 5b: gracefully stop telemetry the instant completion was detected ----------
# EMON: stopped via the official "emon -stop" command (blocks until the collector flushes/exits).
# SocWatch: stopped via a real Ctrl-C signal (no -p-launchable workload to tie its lifetime to).
Write-Host "`nStopping telemetry (EMON: official -stop, SocWatch: graceful Ctrl-C)..." -ForegroundColor Yellow
$emonStopOut = cmd /c 'call "C:\Program Files (x86)\IntelSWTools\emon\sep_vars.cmd" noshell && emon -stop' 2>&1
Write-Host "  EMON stop: $($emonStopOut -join ' ')"
if (-not $socProc.HasExited) {
    $ok = Send-GracefulCtrlC $socProc.Id
    Write-Host "  SocWatch Ctrl-C sent: $ok"
}
Write-Host "  Waiting for EMON/SocWatch to finish finalizing/writing output..."
$socProc.WaitForExit(60000) | Out-Null
Start-Sleep -Seconds 2
$emonStillRunning = Get-Process -Name "emon" -ErrorAction SilentlyContinue
Write-Host "  Telemetry stopped. EMON exited=$(-not [bool]$emonStillRunning)  SocWatch exited=$($socProc.HasExited)" -ForegroundColor Green

# ---------- Step 6: close ALL post-run summary dialogs (never touch Submit) ----------
Write-Host "`n[5/7] Closing benchmark-complete summary dialog(s) (if present)..." -ForegroundColor Yellow
$closedCount = 0
for ($pass = 0; $pass -lt 5; $pass++) {
    $wins = Get-VisibleWindowsForPid $pm.Id
    $summaryDlgs = $wins | Where-Object { $_.Class -eq "#32770" -and $_.Title -eq "" }
    if (-not $summaryDlgs) { break }
    foreach ($d in $summaryDlgs) {
        [Native.Combined]::PostMessage($d.H, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # WM_CLOSE
        $closedCount++
    }
    Start-Sleep -Milliseconds 500
}
Write-Host "  Closed $closedCount summary dialog(s)."

# ---------- Step 7: auto-export results (with retry + freshness verification) ----------
Write-Host "`n[6/7] Triggering 'Save results as text' export..." -ForegroundColor Yellow
$perfRes = "C:\Users\Local_Admin\Documents\PassMark\PerformanceTest10\PerfRes.txt"
$preRunTime = if (Test-Path $perfRes) { (Get-Item $perfRes).LastWriteTime } else { $null }

$exportSucceeded = $false
for ($attempt = 1; $attempt -le 5 -and -not $exportSucceeded; $attempt++) {
    Write-Host "  Attempt $attempt..."
    $hwnd = $pm.MainWindowHandle
    [Native.Combined]::SetForegroundWindow($hwnd) | Out-Null
    Start-Sleep -Milliseconds 300
    [Native.Combined]::PostMessage($hwnd, 0x0111, [IntPtr]40083, [IntPtr]::Zero) | Out-Null  # WM_COMMAND, File > Save results as text

    $dlgHwnd = [IntPtr]::Zero
    for ($try = 0; $try -lt 100; $try++) {
        Start-Sleep -Milliseconds 100
        $wins = Get-VisibleWindowsForPid $pm.Id
        $hit = $wins | Where-Object { $_.Title -match "Save" }
        if ($hit) { $dlgHwnd = $hit[0].H; break }
    }

    if ($dlgHwnd -ne [IntPtr]::Zero) {
        $exportBtn = $null
        for ($try2 = 0; $try2 -lt 20 -and -not $exportBtn; $try2++) {
            $ctrls = Get-ChildControls $dlgHwnd
            $exportBtn = $ctrls | Where-Object { $_.Text -eq "Export" }
            if (-not $exportBtn) { Start-Sleep -Milliseconds 100 }
        }
        if ($exportBtn) {
            [Native.Combined]::PostMessage($exportBtn[0].H, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # BM_CLICK via PostMessage - MUST be non-blocking: clicking Export opens a nested modal "WARNING: file already exists" dialog, and a blocking SendMessage here would freeze this script until that dialog is closed
            Write-Host "    Clicked Export button."

            # PerfRes.txt already exists from the previous run -> PassMark pops up a
            # "WARNING: file already exists, replace it?" dialog (Yes=id6/No=id7). Auto-click Yes.
            $overwriteDlg = [IntPtr]::Zero
            for ($w2 = 0; $w2 -lt 30 -and $overwriteDlg -eq [IntPtr]::Zero; $w2++) {
                Start-Sleep -Milliseconds 150
                $wins3 = Get-VisibleWindowsForPid $pm.Id
                $cand = $wins3 | Where-Object { $_.Class -eq "#32770" -and $_.H -ne $dlgHwnd }
                if ($cand) { $overwriteDlg = $cand[0].H }
            }
            if ($overwriteDlg -ne [IntPtr]::Zero) {
                Write-Host "    [DEBUG] Overwrite WARNING dialog detected ($overwriteDlg) - auto-confirming Yes." -ForegroundColor Cyan
                $ovCtrls = Get-ChildControls $overwriteDlg
                $ovBtn = $ovCtrls | Where-Object { $_.Id -eq 6 }
                if (-not $ovBtn) { $ovBtn = $ovCtrls | Where-Object { $_.Text -match '^&?(Yes|OK)$' } }
                if ($ovBtn) {
                    [Native.Combined]::PostMessage($ovBtn[0].H, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # BM_CLICK via PostMessage (non-blocking)
                    Write-Host "    Clicked Yes on overwrite WARNING."
                } else {
                    [Native.Combined]::PostMessage($overwriteDlg, 0x0111, [IntPtr]6, [IntPtr]::Zero) | Out-Null  # fallback: WM_COMMAND id=6 (Yes)
                    Write-Host "    No button control found - sent default Yes command as fallback."
                }
            }
        } else {
            Write-Host "    Dialog appeared but Export button never showed up." -ForegroundColor Red
        }
    } else {
        Write-Host "    Save dialog did not appear within timeout." -ForegroundColor Red
    }

    # Verify the file actually got refreshed (not stale from a previous run)
    Start-Sleep -Seconds 1
    if (Test-Path $perfRes) {
        $newTime = (Get-Item $perfRes).LastWriteTime
        if (-not $preRunTime -or $newTime -gt $preRunTime) {
            Write-Host "  Export verified fresh (written $newTime)." -ForegroundColor Green
            $exportSucceeded = $true
        } else {
            Write-Host "  File timestamp unchanged ($newTime) - export did not actually happen, retrying..." -ForegroundColor Red
        }
    }
}

if (-not $exportSucceeded) {
    Write-Host "`n  *** FAILED to auto-export PassMark results after 5 attempts. ***" -ForegroundColor Red
    Write-Host "  *** Please manually run File > 'Save results as text...' > Export in PassMark now, then press Enter here. ***" -ForegroundColor Red
    Read-Host "  Press Enter once you've manually exported"
}

# ---------- Step 8: collect results ----------
Write-Host "`n[7/7] Collecting results..." -ForegroundColor Yellow
if (Test-Path $perfRes) {
    $finalTime = (Get-Item $perfRes).LastWriteTime
    if ($preRunTime -and $finalTime -le $preRunTime) {
        Write-Host "  *** WARNING: PerfRes.txt is STALE (not updated since before this run). Results below may be WRONG. ***" -ForegroundColor Red
    }
    Copy-Item $perfRes (Join-Path $resultsDir "PassMark_PerfRes.txt") -Force
    Write-Host "  PassMark results saved (file timestamp: $finalTime)."
} else {
    Write-Host "  WARNING: PerfRes.txt not found at expected path." -ForegroundColor Red
}

# ---------- Restore original power plan ----------
Restore-OriginalPowerPlanOnce
if ($PowerPlan -ne "AsIs" -and $originalScheme -and $appliedPowerPlanName -eq $PowerPlan) {
    Add-Content -Path (Join-Path $resultsDir "system_info.txt") -Value "Restored after run: $($originalScheme.Name)"
}

Write-Host "`n=== DONE ===" -ForegroundColor Cyan
Write-Host "All results in: $resultsDir"
Get-ChildItem -Recurse $resultsDir | Select-Object FullName
if (Test-Path (Join-Path $resultsDir "PassMark_PerfRes.txt")) {
    Write-Host "`n--- PassMark Summary ---"
    Get-Content (Join-Path $resultsDir "PassMark_PerfRes.txt") | Select-String "Mark|Rating"
}
