# PassMark + SocWatch + EMON Automation (Windows)

Fully automated Windows PowerShell scripts that drive **PassMark PerformanceTest 10.2**
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
- PassMark PerformanceTest 10.2 installed.
- For `run_combined_test.ps1` only:
  - Intel EMON / SEP (`C:\Program Files (x86)\IntelSWTools\emon\sep_vars.cmd` must exist).
  - Intel SoC Watch (`socwatch.exe` on `PATH` or in `C:\Program Files\SocWatch`).

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
- `-ConfirmBeforeRun` : ask Y/N before starting the benchmark (default is fully automatic)
- `-SocWatchSafetyCapSeconds` (combined script only, default 900): a hard safety ceiling for
  SocWatch only - **not** the expected run length. In normal operation SocWatch is stopped
  early via Ctrl-C the moment the benchmark finishes; this cap only protects against a
  stuck/undetected completion.

Results are written to a timestamped folder, e.g. `C:\CombinedTest_Results\<yyyyMMdd_HHmmss>\`,
containing `PassMark_PerfRes.txt`, `emon.csv`, and `socwatch*.csv`/`.etl` files.

## How it works

### Completion detection
Both scripts detect benchmark completion by **polling for PassMark's own "benchmark
complete" summary dialog** (the "Submit Baseline" window), not by watching for a CPU usage
plateau - PassMark's workload legitimately has idle gaps between sub-tests, so a CPU-based
heuristic is unreliable. The dialog is closed without ever touching the "Submit Baseline"
button.

### Telemetry start/stop (combined script)
Telemetry duration is **dynamic, not a fixed/guessed timer**:
1. EMON (`emon -C "..." -t1 -l0 ...`) and SocWatch (`socwatch.exe ... -t <SafetyCap>`) are
   started right after PassMark's "Run all tests?" confirmation is accepted - i.e. right as
   the real workload begins.
2. EMON runs an infinite loop (`-l0`) and SocWatch runs under a generous safety-cap timeout;
   neither is expected to hit its own natural stopping point.
3. The instant PassMark's completion dialog is detected, both tools are stopped via a
   **graceful Ctrl-C signal** (confirmed by both tools' own CLI conventions - SocWatch prints
   `"Use Ctrl-C to stop collection"`, EMON finalizes its CSV cleanly on Ctrl-C) - never a
   process kill/`Stop-Process`.
4. This makes captured telemetry duration track the actual benchmark duration, confirmed in
   testing: a benchmark run of ~404s produced a SocWatch `Collection duration (sec): 403.669`.

### Why Ctrl-C via a disposable helper process
Delivering a targeted Ctrl-C to a single child console process on Windows requires
`FreeConsole`/`AttachConsole(targetPid)`/`GenerateConsoleCtrlEvent`. Doing this dance
**inside the same long-lived interactive PowerShell process you're typing into is unsafe** -
it was found to corrupt that process's console handles and crash/close the window after a
couple of uses. Both scripts instead spawn a tiny, separate, hidden `powershell.exe` helper
process whose only job is to attach to the target process's console, fire the Ctrl-C event,
and exit immediately - this can never affect the orchestrating script's own window.

## Safety notes (read before modifying)

- **Never force-kill SocWatch or EMON mid-collection.** A prior incident correlated a forced
  kill of SocWatch with a `CRITICAL_PROCESS_DIED` BSOD. Always use the documented graceful
  stop (Ctrl-C for both tools here; EMON also supports `emon -stop`).
- **Never run SocWatch interactively/exploratorily just to "check" something** (e.g.
  `--help`) without a plan - this has caused a full system hang requiring a hard power-cycle
  reboot in testing. Treat it like any other kernel-driver-backed collection tool: only
  invoke it via the confirmed-safe start/stop patterns in these scripts.
- `sep_vars.cmd` must be invoked with its **full absolute path** when calling it via
  `cmd /c` from PowerShell - a bare `sep_vars.cmd` after `cd` is not reliably found.
- Each EMON/SocWatch process is launched with `-WindowStyle Minimized` (not `-NoNewWindow`)
  so each gets its own distinct console, which the Ctrl-C helper process can target
  independently without affecting the other.

## Known limitations / open items

- EMON is launched via a `cmd.exe /c "call sep_vars.cmd && emon ..."` wrapper; the Ctrl-C
  helper targets the `cmd.exe` PID (not the inner `emon.exe` PID). This has worked reliably
  in testing (console is shared between parent and child), but hasn't been proven under every
  EMON version/config.
- SocWatch can take a couple of minutes **after** receiving Ctrl-C to finish flushing large
  ETL sessions before its process actually exits. The combined script does not block waiting
  for that (it proceeds to close PassMark dialogs/export once its own short wait elapses) -
  this is expected and does not affect the already-written files.
