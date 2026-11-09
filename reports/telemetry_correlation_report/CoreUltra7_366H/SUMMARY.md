# Test Summary

Quick overview of the platform, silicon and results. Details, plots and
correlations: [TELEMETRY_CORRELATION_REPORT.md](TELEMETRY_CORRELATION_REPORT.md).

## Platform

Metric correction: the column previously labeled IPC is instructions per
unhalted reference cycle (`INST_RETIRED.ANY / CPU_CLK_UNHALTED.REF_TSC`),
not instructions per actual core cycle. Values are unchanged. The archived
EMON captures lack actual-cycle counters, so conventional IPC is unavailable.
Derived CSVs now use `instructions_per_ref_cycle` and
`avg_instructions_per_ref_cycle`; run averages equally weight valid
core/sample ratios and exclude zero-reference samples.

| Item | Value |
|---|---|
| CPU (Si) | Intel Core Ultra 7 366H, 16 cores / 16 threads (1 thread per core), 1 socket |
| CPU base operating frequency | 3800 MHz (per SoC Watch) |
| Memory | 64 GB: 2 x 32 GB DDR5 SK Hynix @ 6400 MT/s |
| BIOS | PTLPFWI1.R00.3515.D56.2601280733 (01/27/2026) |
| GPU | Intel(R) Graphics, driver 32.0.101.8357 |
| OS | Windows 11 Enterprise LTSC, Build 26100 (64-bit) |
| Tools | PassMark PerformanceTest 10.2, EMON V11.61, SoC Watch v2026.2.0 |

## Test setup

All runs: `.\run_combined_test.ps1 -TestDuration Short -TestIterations 3 -PowerPlan <plan>`
with EMON + SoC Watch running. Date: 2026-11-03/04. Windows has no exposed
per-core EPP/governor setting on this hardware (`powercfg` `PERFEPP`/`PERFBOOSTMODE`
both return "Invalid Parameters"), so the only available lever is the whole
power plan (`powercfg`), unlike Linux's separate profile + governor axes.
`Balanced` was not re-run this round. An older `Balanced` run exists from a
prior session, but its CPU Mark (~23.5k) is far below all three plans here
(~34k) while its other scores are comparable or higher - inconsistent with
power-plan ordering (Balanced should not be slower than `PowerSaver` on CPU
Mark) and likely reflects different test conditions in that older session. It
has been excluded from this report/table rather than mixed in; re-run
`Balanced` under the same conditions as the three plans above if a clean
comparison point is needed.

## Results

| Run | Power plan | CPU Mark | Memory Mark | PassMark Rating | Avg pkg power | Avg active freq | instructions/ref cycle |
|---|---|---|---|---|---|---|---|
| 20261103_213137 | HighPerformance | 34164 | 3722 | 6427.0 | 17.9 W | 3307 MHz | 1.01 |
| 20261103_231839 | UltimatePerformance | 34356 | 3664 | 6315.2 | 17.6 W | 3297 MHz | 0.95 |
| 20261103_233441 | PowerSaver | 33906 | 2966 | 5121.0 | 13.8 W | 2899 MHz | 0.78 |

\* `HighPerformance`'s collection window ran longer than the other two (same
`-TestDuration Short -TestIterations 3` settings) - its scores/averages are
still valid (PassMark composite marks are throughput rates, not duration-scaled),
but the sample counts aren't directly comparable across rows.

## Key findings

- **HighPerformance and UltimatePerformance are essentially tied** (CPU Mark
  within 0.6%, Rating within 1.8%, package power within 2%). This matches the
  earlier finding that this CPU/driver stack exposes no distinct EPP/governor
  setting - Windows power plans mostly change ACPI platform-profile-style
  limits, and `UltimatePerformance` vs `HighPerformance` barely differ in
  practice on this hardware.
- **PowerSaver's hit to raw CPU throughput is small**: CPU Mark is only about
  0.8% lower than HighPerformance, at about 23% less package power (13.8 W vs
  17.9 W) and about 12% lower average active frequency. This is a much
  smaller compute penalty than Linux's `power-saver` profile (which dropped
  CPU Mark by about 52% at about 74% less power) - Windows' PowerSaver plan
  appears to mainly cap sustained boost/P-state ceiling rather than force a
  low-power operating point throughout.
- **Memory Mark and overall Rating are where PowerSaver costs the most**:
  Memory Mark is about 20% lower and PassMark Rating about 20% lower than
  HighPerformance, driven by subsystems other than raw CPU compute.
- **instructions/ref cycle drops noticeably under PowerSaver** (0.78 vs 1.01 on HighPerformance,
  about 23% lower), consistent with the lower average active frequency and a
  less aggressive P-state response.

## Updating this summary

Re-run `cross_run_analysis.py Results/`, copy the new report/plots/CSV into
`reports/telemetry_correlation_report/CoreUltra7_366H/` (see the README), then
update the tables above.
