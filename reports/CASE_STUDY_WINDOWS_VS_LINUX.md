# Case Study: PassMark Workload and Telemetry on Windows and Linux

Same silicon (Intel Core Ultra 7 366H, Panther Lake), same board/BIOS, same
memory config, same EMON version (V11.61), run with this repo's sibling
project [`passmark-socwatch-emon-linux`](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux).
PassMark is the workload and score source; SoC Watch and EMON provide
supporting measurements of platform behavior during the captures. The goal
is to describe the relationship between scores, power, frequency and CPU
activity under the tested configurations on Intel Core Ultra 7 366H.
This is an **exploratory case study**, not an OS ranking or a controlled
apples-to-apples benchmark - see [Caveats](#caveats--limitations).

- Windows source: [`telemetry_correlation_report/CoreUltra7_366H/SUMMARY.md`](telemetry_correlation_report/CoreUltra7_366H/SUMMARY.md)
- Linux source: [`CoreUltra7_366H/SUMMARY.md`](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux/blob/main/reports/telemetry_correlation_report/CoreUltra7_366H/SUMMARY.md)

## Scope and workload equivalence

**Stage 1 examines PassMark results separately within Windows and within
Ubuntu. There is no head-to-head OS comparison in this stage.** Scores are
the starting point; SoC Watch and EMON provide context for each workload
capture. OS, scheduler and power-management mechanisms are later research
questions, not explanations established by the current observations.

Windows uses the GUI application; Ubuntu uses the Linux CLI build. This
interface difference alone does not prove that the underlying CPU/Memory
tests differ, but matching names such as CPU Mark and Memory Mark do not
prove equivalent work either. Sub-test algorithms, implementation, compiler
optimizations, threading, scoring and executed work have not been audited
for equivalence. Windows' overall PassMark Rating is not interchangeable
with the Linux CPU/Memory marks; different suite coverage or workload phases
can also affect whole-run telemetry.

The configurations are settings tested on this platform, not established
optima or proof of either OS's maximum achievable performance. Matching
power-profile names or limits would not establish workload equivalence.

## Run selection

**Windows `HighPerformance` (20261103_213137) is retained as reference-only
and excluded from the primary comparison below because its iteration count
differs from the other Windows runs.** The operator's corrected settings are
three iterations for HighPerformance, one each for UltimatePerformance and
PowerSaver, and three for all Ubuntu runs. This supersedes the earlier
32-iteration statement and the archived summary's claim of three iterations
for every Windows plan. These settings are operator-reported, not independently
verified from recorded invocation metadata.

Windows comparisons now use `UltimatePerformance` as the reference for
`PowerSaver`. No raw files or archived analysis CSVs have been removed or
regenerated; those CSVs and the linked historical summaries still include
HighPerformance. Its exclusion does not mean the capture is invalid; its
three iterations match Ubuntu's count, but not the retained Windows pair's
one iteration. Neither matching counts nor dividing capture time by the
iteration count establishes cross-OS workload equivalence.

## Evidence and traceability

| Source | Evidence used here | Interpretation boundary |
|---|---|---|
| PassMark | CPU/Memory marks and exported sub-test scores | Describes the benchmark outcome, not the cause of a score difference |
| SoC Watch | Collection duration, average package power, active frequency and package C0 residency | Whole-capture behavior, not telemetry isolated to a CPU or Memory sub-test |
| EMON | Exported counters and derived IPC/cache metrics | Requires verified event definitions, aggregation and phase alignment before cross-OS interpretation |
| System information | Hardware, OS and recorded power settings | Configuration context, not proof that effective policies are equivalent |

Windows backing data lives in the [SKU archive](telemetry_correlation_report/CoreUltra7_366H/):
each run contains `PassMark_PerfRes.txt`, `socwatch.csv`, `emon.csv`,
`system_info.txt` and `analysis/emon_timeseries_tidy.csv`.
The [Linux SKU archive](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux/tree/main/reports/telemetry_correlation_report/CoreUltra7_366H)
contains `results_console_all.yml`, `socwatch/socwatch.csv`, `emon.csv`,
`system_info.txt` and the tidy EMON CSV per run. Linux scores here use the
console-derived YAMLs; native PassMark YAML exports can be stale under
telemetry capture and are not the score authority for this comparison.

The [Windows analysis CSV](telemetry_correlation_report/CoreUltra7_366H/cross_run_analysis/combined_runs.csv)
and [Linux analysis CSV](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux/blob/main/reports/telemetry_correlation_report/CoreUltra7_366H/cross_run_analysis/combined_runs.csv)
provide the per-run telemetry used below. They are derived data, not raw
captures. Score columns in a derived CSV should be checked against the
per-run score artifacts before reuse.

| OS / configuration | Run IDs |
|---|---|
| Windows `HighPerformance` (reference-only) | 20261103_213137 |
| Windows `UltimatePerformance` | 20261103_231839 |
| Windows `PowerSaver` | 20261103_233441 |
| Linux `performance`, `powersave` governor | 20261104_073216, 20261104_080450, 20261104_081815 |
| Linux `performance`, `performance` governor | 20261104_075827, 20261104_081132, 20261104_082458 |
| Linux `power-saver` | 20261104_073659 |

Raw data permits further investigation, but its presence
does not itself establish aligned workload phases or metric equivalence.
The inspected score export and SoC Watch summary do not identify individual
iteration boundaries; timestamped benchmark markers aligned with telemetry
would be needed to measure iteration or sub-test durations.

## Platform (shared)

| Item | Value |
|---|---|
| CPU | Intel Core Ultra 7 366H, 16 cores / 16 threads, 1 socket |
| Memory | 64 GB: 2 x 32 GB DDR5 SK Hynix @ 6400 MT/s |
| BIOS | PTLPFWI1.R00.3515.D56.2601280733 |
| EMON | V11.61 (both) |
| SoC Watch | v2026.2.0 (Windows) / v2026.2 pre-release (Linux) |
| Windows OS | Windows 11 Enterprise LTSC, Build 26100 |
| Linux OS | Ubuntu 24.04.5 LTS, Linux 6.18-intel |
| Windows power control | Whole power plan via `powercfg`; EPP/boost-setting queries were unsuccessful in this test setup |
| Linux power control | `powerprofilesctl` profile + `intel_pstate` governor (separate axes) |
| Windows test dates | 2026-11-03/04 |
| Linux test date | 2026-11-04 |

Windows used PassMark PerformanceTest 10.2; the Linux summary identifies the
CLI build but does not record its version. The runs use Short duration;
the retained Windows pair used one iteration each, while Ubuntu used three,
per the operator clarification above. Equivalence of the benchmark builds,
sub-tests and process/thread settings has not yet been established.

## Windows: PassMark observations

Reference: `UltimatePerformance`. HighPerformance remains reference-only as
explained in Run selection. Each row represents one independent capture;
Runs does not count iterations within a capture. Package power is converted
from mW to W, and displayed values are rounded after calculation.

| Configuration | Runs | CPU Mark | Memory Mark | Avg pkg power | Avg active freq | IPC |
|---|---|---|---|---|---|---|
| `UltimatePerformance` | 1 | 34356 | 3664 | 17.6 W | 3297 MHz | 0.95 |
| `PowerSaver` | 1 | 33906 | 2966 | 13.8 W | 2899 MHz | 0.78 |

### Score observations

- Against UltimatePerformance, PowerSaver records ~1.3% lower CPU Mark and
  ~19.0% lower Memory Mark. These are observations from one capture per plan.
- The composite CPU Mark hides different sub-test responses. Integer Math
  falls from 85488.8 to 75935.6 MOps/s (~11.2%), and CPU Single Threaded falls
  from 4475.0 to 3639.7 MOps/s (~18.7%). Compression rises from 316608.0 to
  357559.2 KBytes/s (~12.9%). Repeat testing is needed before attributing
  these differences to the selected plan.

### Supporting telemetry

PowerSaver records ~21.3% lower average package power and lower active
frequency. Package C0 residency is 73.67% for UltimatePerformance and 88.97%
for PowerSaver. These describe the full captures, not isolated CPU or Memory
sub-tests. They do not establish energy per unit of work, CPU utilization,
or a causal explanation for the score changes.

## Ubuntu: PassMark observations

Reference: `performance` profile with the `powersave` governor. Performance
rows are equal-weight means of three independent captures, not pooled
telemetry samples. The power-saver row is one capture. Scores use the
console-derived YAMLs; telemetry uses the analysis CSV values, averaged
before rounding. Package power is converted from mW to W.

| Configuration | Runs | CPU Mark | Memory Mark | Avg pkg power | Avg active freq | IPC |
|---|---|---|---|---|---|---|
| `performance` profile, `powersave` governor | 3 | 30732 | 3772 | 21.6 W | 2947 MHz | 1.63 |
| `performance` profile, `performance` governor | 3 | 29891 | 3763 | 21.6 W | 2932 MHz | 1.58 |
| `power-saver` profile, `powersave` governor | 1 | 14610 | 1512 | 5.6 W | 1234 MHz | 0.70 |

### Score observations

- Against the reference, the power-saver capture records ~52% lower CPU Mark
  and ~60% lower Memory Mark. This configuration has only one capture.
- With the performance profile unchanged, the performance-governor group
  records ~2.7% lower CPU Mark and similar Memory Mark. The cause is not
  established; the governor's name does not predict the benchmark outcome.
- Repeated CPU Marks within each performance configuration agree within
  ~0.4%. This supports describing those groups, not assuming equivalent
  repeatability for the single power-saver capture.

### Supporting telemetry

The power-saver capture records ~74% lower average package power and an
active frequency of about 1234 MHz, against the reference's 2947 MHz.
Package C0 residency remains near 99% across these configurations. The score,
power and frequency changes accompany each other in these captures; they
do not establish proportional scaling or isolate a power-management cause.
IPC is retained as workload context within Ubuntu, not an OS ranking metric.

## Next investigation

First repeat the within-OS configurations and inspect PassMark sub-test
responses, suite coverage and score aggregation. Then align workload-phase
markers with SoC Watch and EMON time series to determine which measurements
belong to each sub-test. Collection duration alone is not a phase marker.

Only after that should OS, power-policy, scheduler or compiler mechanisms be
investigated as possible explanations. The current stage neither attributes
the differences to those mechanisms nor compares the two OSes head to head.

## Caveats / limitations

- **Not a controlled single-script comparison** - two independent repos, run
  on different dates, with different harness implementations
  (`run_combined_test.ps1` vs `run_combined_test.sh`) and partially different
  SoC Watch versions (pre-release vs release).
- **Iteration counts differ.** Windows HighPerformance used three iterations;
  UltimatePerformance and PowerSaver used one each; Ubuntu used three per run,
  per the operator. HighPerformance is reference-only for the current Windows
  pair comparison. Thermal and phase weighting can change with run length,
  even for rate-based scores. Normalizing total capture duration does not
  provide measured per-iteration timings or remove these differences.
- **Windows has n=1 per retained plan; Linux has n=3 per performance configuration and
  n=1 for power-saver.** Linux's repeated CPU Marks agree within ~0.4%; that
  does not establish repeatability for either OS's single-run configurations.
- **IPC comparability is unverified** (see above): EMON event definitions,
  aggregation and collection windows have not been aligned.
- Conclusions here are **directional observations for further investigation**,
  not a certified OS power-efficiency comparison.

## Updating this case study

Regenerate analysis from each repo's `Results/`, refresh its SKU archive and
summary, then update the tables above by hand; this file is not auto-generated.
Filter out Windows run `20261103_213137` when deriving this comparison from
the historical CSVs for the primary Windows pair comparison. To compare all
Windows plans at matching iteration counts, rerun HighPerformance with one
iteration, or UltimatePerformance and PowerSaver with three. Record invocation
settings and iteration/sub-test timestamps, then update run IDs, source
references and affected comparisons. Three iterations for all configurations
would also match Ubuntu's iteration setting, without proving workload equivalence.
Before a controlled follow-up comparison, verify benchmark versions and
sub-test implementations, scoring and suite coverage, process/thread counts,
effective power settings, matched telemetry
start/stop windows and EMON event definitions. Repeat every configuration
under comparable thermal/background conditions and record energy over the
same workload if making an energy-efficiency claim.
