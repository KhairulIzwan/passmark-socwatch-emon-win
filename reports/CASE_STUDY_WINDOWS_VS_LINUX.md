# Case Study: Windows vs. Linux Power-Plan Behavior on Intel Core Ultra 7 366H

Same silicon (Intel Core Ultra 7 366H, Panther Lake), same board/BIOS, same
memory config, same EMON version (V11.61), run with this repo's sibling
project [`passmark-socwatch-emon-linux`](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux).
This is an **exploratory case study**, not a controlled apples-to-apples
benchmark - see [Caveats](#caveats--limitations) before drawing conclusions.

- Windows source: [`telemetry_correlation_report/CoreUltra7_366H/SUMMARY.md`](telemetry_correlation_report/CoreUltra7_366H/SUMMARY.md)
- Linux source: [`passmark-socwatch-emon-linux/reports/SUMMARY.md`](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux/blob/main/reports/SUMMARY.md)

## Platform (shared)

| Item | Value |
|---|---|
| CPU | Intel Core Ultra 7 366H, 16 cores / 16 threads, 1 socket |
| Memory | 64 GB: 2 x 32 GB DDR5 SK Hynix @ 6400 MT/s |
| BIOS | PTLPFWI1.R00.3515.D56.2601280733 |
| EMON | V11.61 (both) |
| SoC Watch | v2026.2.0 (Windows) / v2026.2 pre-release (Linux) |
| OS | Windows 11 Enterprise LTSC, Build 26100 | Ubuntu 24.04.5 LTS, Linux 6.18-intel |
| Power control model | Whole power plan via `powercfg` (no separate EPP/governor) | `powerprofilesctl` profile + `intel_pstate` governor (separate axes) |
| Test dates | 2026-11-03/04 | 2026-11-04 |

## Top performance mode

| | CPU Mark | Memory Mark | Avg pkg power | Avg active freq | IPC |
|---|---|---|---|---|---|
| Win `HighPerformance` | 34164 | 3722 | 17.9 W | 3307 MHz | 1.01 |
| Win `UltimatePerformance` | 34356 | 3664 | 17.6 W | 3297 MHz | 0.95 |
| Linux `performance` profile, `powersave` governor | 30732 | 3772 | 21.6 W | 2950 MHz | 1.64 |
| Linux `performance` profile, `performance` governor | 29891 | 3763 | 21.7 W | 2933 MHz | 1.58 |

- Windows reaches **~11-12% higher CPU Mark at ~20% less package power** than
  Linux's best configuration measured here.
- Memory Mark is nearly identical across OSes (~3700s) - this subsystem looks
  largely OS-independent, as expected (DRAM bandwidth/latency bound, not
  scheduler/power-policy bound).
- IPC is **inverted** relative to CPU Mark: Linux reports much higher IPC
  (~1.6) at lower average clocks yet a lower CPU Mark than Windows (~1.0 IPC,
  higher clocks, higher CPU Mark). This is the strongest signal that the two
  platforms' EMON "IPC" metric is **not measuring the same thing** (different
  EMON event-set/config per OS) - treat IPC as OS-internal only, never compare
  it directly across this table.

## Lowest-power mode

| | CPU Mark drop vs. own top mode | Memory Mark drop | Package power cut |
|---|---|---|---|
| Win `PowerSaver` | ~0.8% | ~20% | ~23% (17.9 W -> 13.8 W) |
| Linux `power-saver` profile | ~52% | ~60% | ~74% (21.6 W -> 5.6 W) |

This is the headline, highest-confidence finding of the case study:
**Linux's `power-saver` profile is a dramatically more aggressive throttle**
than Windows' `PowerSaver` plan on the same silicon. Linux crashes average
active frequency to ~1234 MHz (from ~2950 MHz); Windows only drops to
~2899 MHz (from ~3307 MHz). Windows' lowest power plan mostly costs Memory
Mark/overall Rating, while leaving sustained CPU compute throughput almost
untouched; Linux's lowest profile cuts compute roughly in proportion to the
power cut.

## Why this might be happening

- Windows power plans (`powercfg`) appear to act more like coarse ACPI
  platform-profile hints than a true per-core EPP/governor lever on this
  machine - confirmed separately in this repo (`PERFEPP`/`PERFBOOSTMODE` both
  return "Invalid Parameters" via `powercfg`). Linux's `power-saver` directly
  sets EPP to `power` and the ACPI platform profile to `low-power`, which
  appears to have a much stronger effect on sustained frequency than whatever
  Windows' `PowerSaver` plan changes.
- This would explain both halves of the result: Windows' top mode doesn't
  need to pull as much power because it isn't forcing as aggressive a boost
  policy as Linux's `performance` EPP, and Windows' bottom mode doesn't drop
  as much because it isn't forcing as aggressive a throttle policy as Linux's
  `power-saver` EPP.

## Caveats / limitations

- **Not a controlled single-script comparison** - two independent repos, run
  on different dates, with different harness implementations
  (`run_combined_test.ps1` vs `run_combined_test.sh`) and partially different
  SoC Watch versions (pre-release vs release).
- **Windows `HighPerformance` run had a ~3x longer collection window** than
  the other two Windows runs despite identical `-TestIterations 3` settings
  (not root-caused - see this repo's `SUMMARY.md`/`TELEMETRY_CORRELATION_REPORT.md`).
  The composite scores are still valid (rate-based, not duration-scaled), but
  sample-count-sensitive metrics should be read with that in mind.
  - **n=1 per configuration on both sides** (Windows plans in this round;
  Linux's `power-saver` row). Linux's `performance` config does have 3 repeats
  agreeing within ~0.4%, giving more confidence in that side's numbers; the
  Windows and Linux `power-saver` numbers are each single runs.
- **IPC is not cross-OS-comparable** (see above) - likely different EMON
  event/metric definitions per OS, not a real hardware difference.
- Conclusions here are **directional observations for further investigation**,
  not a certified OS power-efficiency comparison.

## Updating this case study

Re-run the latest `SUMMARY.md` in both repos, then update the tables above by
hand - this file is not auto-generated.
