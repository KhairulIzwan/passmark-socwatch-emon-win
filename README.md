# PassMark + SocWatch + EMON Automation (Windows)

Fully automated Windows PowerShell scripts that drive **PassMark PerformanceTest 10.2 / 11.1**
end-to-end (launch, configure, run, export results) using raw Win32 message automation
(`PostMessage`/`SendMessage` against menu and dialog control IDs), since PassMark's UI is
custom-drawn and not exposed via standard UI Automation.

Two scripts are provided:

| Script | Purpose |
|---|---|
| `run_passmark_auto.ps1` | Standalone PassMark automation only (no telemetry). |
| `run_combined_test.ps1` | PassMark automation **plus** EMON + SocWatch telemetry capture, dynamically started/stopped to match the actual benchmark run time. |

## Requirements

- Windows, run from an **elevated, interactive** PowerShell session (not SYSTEM/session 0 -
  the scripts post raw window messages and need a real desktop/console).
- PassMark PerformanceTest 10.2 or 11.1 installed (both verified; the report archive notes which version each run used).
- For `run_combined_test.ps1` only:
  - Intel EMON / SEP (`C:\Program Files (x86)\IntelSWTools\emon\sep_vars.cmd` must exist).
  - Intel SoC Watch (`socwatch.exe` on `PATH` or in `C:\Program Files\SocWatch`).

### Getting and installing EMON and SocWatch (combined script only)

Both are portable zips from the internal telemetry share (Intel network/VPN required; no
installer - copy into place from an **elevated** PowerShell). Newer builds may exist in the
same folders - check there first.

| Tool | Download |
|---|---|
| EMON 11.61 | `http://10.221.202.144/OOC_OnePnP/Telemetry/Windows/EMON/emon_nda_11.61_win_08201055109fdd6c1.zip` |
| SocWatch 2026.6.0 | `http://10.221.202.144/OOC_OnePnP/Telemetry/Windows/SocWatch/2026-11-10/socwatch_windows_INTERNAL_v2026.6.0.zip` |

```powershell
$t = "$env:USERPROFILE\Downloads\telemetry"; New-Item -ItemType Directory $t -Force | Out-Null
# 1. Download (add -Proxy $null if the system proxy blocks the internal host)
Invoke-WebRequest "<EMON url>" -OutFile "$t\emon.zip"
Invoke-WebRequest "<SocWatch url>" -OutFile "$t\socwatch.zip"
Expand-Archive "$t\emon.zip" "$t\emon" -Force
Expand-Archive "$t\socwatch.zip" "$t\socwatch" -Force

# 2. Install to the paths the combined script expects (elevated)
New-Item -ItemType Directory "C:\Program Files (x86)\IntelSWTools" -Force | Out-Null
Copy-Item (Get-ChildItem "$t\emon" -Directory | Select -First 1).FullName "C:\Program Files (x86)\IntelSWTools\emon" -Recurse
$sw = (Get-ChildItem "$t\socwatch" -Directory | Select -First 1).FullName
Copy-Item "$sw\64" "C:\Program Files\SocWatch" -Recurse

# 3. Register + start the EMON sampling drivers (one-time, elevated; persists across reboots)
cmd /c 'call "C:\Program Files (x86)\IntelSWTools\emon\sep_vars.cmd" noshell && sepreg -i -v'
# 4. Verify - must print "SEP Driver Version: 5.61" / "PAX Driver Version" (not "Error retrieving")
cmd /c 'call "C:\Program Files (x86)\IntelSWTools\emon\sep_vars.cmd" noshell && emon -v'
```

If `sepreg -i` reports the driver is not properly signed or fails to start, Memory Integrity
(HVCI, Windows Security > Device security > Core isolation) is likely blocking it - turn it off
and reboot. Note: with Hyper-V + VBS enabled EMON still works but some core/uncore PMU event
counts can read 0 (EMON release notes).

Only run `emon`/`socwatch` through the scripts (see Safety notes). SocWatch loads its driver
on first collection and needs admin.

## Usage

```powershell
# PassMark only
.\run_passmark_auto.ps1 -TestDuration Short -TestIterations 1

# PassMark + EMON + SocWatch telemetry
.\run_combined_test.ps1 -TestDuration Short -TestIterations 1
```

Common parameters:
- `-TestDuration` : `Short | Medium | Long | VeryLong` (PassMark preference)
- `-TestIterations` : number of repeats per sub-test
- `-PassMarkExe`, `-PerfResDir` : PassMark executable and export folder. By default the folder is
  `<Documents>\PassMark\PerformanceTest<major version of the exe>` (e.g. `PerformanceTest11`).
- `-CmdPreferences`, `-CmdRunAll`, `-CmdSaveText` : menu `WM_COMMAND` ids (defaults 40040/40079/40083
  are verified on v10.2 and v11.1). For other versions run `.\probe_menu.ps1` in an interactive
  window to list the real ids and pass them in.
- `-ConfirmBeforeRun` : ask Y/N before starting the benchmark (default is fully automatic)
- `-SocWatchSafetyCapSeconds` (combined script only, default 900): a hard safety ceiling for
  SocWatch only - **not** the expected run length. In normal operation SocWatch is stopped
  early via Ctrl-C the moment the benchmark finishes; this cap only protects against a
  stuck/undetected completion.
- `-PowerPlan` (combined script only, default `HighPerformance`): power plan to use **during**
  the benchmark - `AsIs | Balanced | HighPerformance | UltimatePerformance | PowerSaver`. The
  original plan is always restored afterward (even on a mid-run error, via a `trap` safety
  net). `Balanced` (Windows default) throttles for power savings and can make benchmark runs
  inconsistent run-to-run; `HighPerformance`/`UltimatePerformance` remove that throttling.
  `UltimatePerformance` is auto-unhidden via `powercfg -duplicatescheme` if not already present.
  `HighPerformance` is created the same way on systems that don't list it (e.g. Balanced-only).

Results are written to a timestamped folder inside the project itself, e.g.
`passmark-socwatch-emon-win\Results\<yyyyMMdd_HHmmss>\` (next to the script, via
`$PSScriptRoot`), containing `PassMark_PerfRes.txt`, `emon.csv`, `socwatch.csv`,
`socwatch_WakeupAnalysis.csv`, and `system_info.txt` (combined script only - see below).
The raw SocWatch `.etl` ETW trace files (can be multiple GB) are automatically deleted once
the CSV summaries are confirmed present - they're not human-readable and aren't used by
`analyze_run.py` (they're kept only if the CSVs failed to generate, for diagnosis).
`Results/` is git-ignored, so run output is never committed/pushed - only the scripts/reports
are version-controlled.

### Test-bed configuration snapshot (`system_info.txt`, combined script only)
Every run of `run_combined_test.ps1` captures a `system_info.txt` into the results folder with
the CPU model/cores/threads, installed RAM (size/speed/manufacturer per module), BIOS
version/date, OS build, GPU model + driver version, and which power plan was active
originally vs. during the run - the baseline hardware/software configuration info needed to
make sense of (and reproduce) a given benchmark's numbers.

## How it works

### Completion detection
Both scripts detect benchmark completion by **polling for PassMark's own "benchmark
complete" summary dialog** (the "Submit Baseline" window), not by watching for a CPU usage
plateau - PassMark's workload legitimately has idle gaps between sub-tests, so a CPU-based
heuristic is unreliable. The dialog is closed without ever touching the "Submit Baseline"
button.

### Telemetry start/stop (combined script)
Telemetry duration is **dynamic, not a fixed/guessed timer**:
1. EMON (`emon -nb -C "..." -t1 -l0 ...`) and SocWatch (`socwatch.exe -f ... -t <SafetyCap>`)
   are started right after PassMark's "Run all tests?" confirmation is accepted - i.e. right
   as the real workload begins. Flag sets for both tools were verified against the
   organization's reference SocWatch/EMON/SPEC CPU2017 automation scripts.
2. EMON is launched with `-nb` (non-blocking/detached - returns control to the launching
   `cmd.exe` in ~2s while it keeps sampling in the background, matching the reference
   automation pattern) and loops forever (`-l0`, 1-second samples). SocWatch collects 14
   telemetry channels (`cpu-wakeup`, `sys-memory`, `cpu-freq`, `uncore-freq`, `cpu-ipc`,
   `cache`, `os-cpu-pstate`, `hw-cpu-pstate`, `pkg-pwr`, `cpu-pstate`, `gfx-pstate`,
   `sa-freq`, `pwr-limits`, `cpu-cstate`) under a generous safety-cap timeout; neither is
   expected to hit its own natural stopping point.
3. The instant PassMark's completion dialog is detected:
   - **EMON** is stopped via the official, documented `emon -stop` command (blocks until the
     background collector flushes and exits cleanly - verified to produce a clean multi-sample
     CSV, same as the reference automation scripts).
   - **SocWatch** is stopped via a **graceful Ctrl-C signal** (SocWatch itself prints
     `"Use Ctrl-C to stop collection"`; verified clean output on a live test). SocWatch has no
     equivalent detached+stop command usable here because the reference's `-p`/auto-stop
     mechanism requires a single launchable blocking workload process, which PassMark's
     GUI-driven automation (Win32 message clicks) doesn't provide.
   - Neither tool is ever force-killed/`Stop-Process`'d.
4. This makes captured telemetry duration track the actual benchmark duration, confirmed in
   testing: a benchmark run of ~404s produced a SocWatch `Collection duration (sec): 403.669`.

### Why Ctrl-C via a disposable helper process (SocWatch)
Delivering a targeted Ctrl-C to a single child console process on Windows requires
`FreeConsole`/`AttachConsole(targetPid)`/`GenerateConsoleCtrlEvent`. Doing this dance
**inside the same long-lived interactive PowerShell process you're typing into is unsafe** -
it was found to corrupt that process's console handles and crash/close the window after a
couple of uses. The script instead spawns a tiny, separate, hidden `powershell.exe` helper
process whose only job is to attach to the target process's console, fire the Ctrl-C event,
and exit immediately - this can never affect the orchestrating script's own window. EMON no
longer needs this trick since it is stopped via the official `emon -stop` command instead.

## Safety notes (read before modifying)

- **Never force-kill SocWatch or EMON mid-collection.** A prior incident correlated a forced
  kill of SocWatch with a `CRITICAL_PROCESS_DIED` BSOD. Always use the documented graceful
  stop (`emon -stop` for EMON, Ctrl-C for SocWatch).
- **Never run SocWatch interactively/exploratorily just to "check" something** (e.g.
  `--help`) without a plan - this has caused a full system hang requiring a hard power-cycle
  reboot in testing. Treat it like any other kernel-driver-backed collection tool: only
  invoke it via the confirmed-safe start/stop patterns in these scripts.
- `sep_vars.cmd` must be invoked with its **full absolute path** when calling it via
  `cmd /c` from PowerShell - a bare `sep_vars.cmd` after `cd` is not reliably found.
- Each EMON/SocWatch process is launched with `-WindowStyle Minimized` (not `-NoNewWindow`)
  so each gets its own distinct console, which the Ctrl-C helper process can target
  independently without affecting the other.

## Example analysis

[`reports/telemetry_correlation_report/Core5_223PE/TELEMETRY_CORRELATION_REPORT.md`](reports/telemetry_correlation_report/Core5_223PE/TELEMETRY_CORRELATION_REPORT.md) and [`reports/telemetry_correlation_report/CoreUltra7_366H/TELEMETRY_CORRELATION_REPORT.md`](reports/telemetry_correlation_report/CoreUltra7_366H/TELEMETRY_CORRELATION_REPORT.md)
is a worked example (generated by the analysis scripts) correlating PassMark scores against
SocWatch/EMON telemetry across 5 runs on 3 different power plans (CoreUltra7_366H: 3 runs on
PassMark 10.2 plus 2 runs on PassMark 11.1, labeled per run in a "Tool Versions per Run" table) -
test-bed config, per-run
plots, cross-run comparison, and correlation findings. Raw per-run telemetry (`Results/`) is
git-ignored as usual; this report + its plots are committed since they're the shareable output.

[`reports/WINDOWS_VS_UBUNTU_BEST_SCORE.md`](reports/WINDOWS_VS_UBUNTU_BEST_SCORE.md) is a short
best-score comparison (CPU/Memory Mark and CPU sub-tests) of Windows vs. Ubuntu on the same SKU.

[`reports/CASE_STUDY_WINDOWS_VS_LINUX.md`](reports/CASE_STUDY_WINDOWS_VS_LINUX.md) is an
exploratory cross-OS comparison of this repo's results against the sibling
[`passmark-socwatch-emon-linux`](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux)
repo on the same silicon.

## Known limitations / open items

- EMON is launched via a `cmd.exe /c "call sep_vars.cmd && emon -nb ..."` wrapper; `-nb`
  detaches the actual collector from that `cmd.exe`, so the launching process exits quickly
  on its own - this is expected, not an error. The collector is tracked/stopped by name
  (`emon -stop`), not by PID.
- SocWatch can take a couple of minutes **after** receiving Ctrl-C to finish flushing large
  ETL sessions before its process actually exits. The combined script does not block waiting
  for that (it proceeds to close PassMark dialogs/export once its own short wait elapses) -
  this is expected and does not affect the already-written files.
