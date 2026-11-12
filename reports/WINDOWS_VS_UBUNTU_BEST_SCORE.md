# Windows vs. Ubuntu: Best PassMark Score (Core Ultra 7 366H)

Short comparison of the **best PassMark score each OS reached** on this SKU
(Intel Core Ultra 7 366H, Panther Lake, same board/BIOS/memory). Scores only,
with a CPU sub-test breakdown. For the wider exploratory study (telemetry,
caveats) see [CASE_STUDY_WINDOWS_VS_LINUX.md](CASE_STUDY_WINDOWS_VS_LINUX.md).

## Runs compared

| | Windows | Ubuntu |
|---|---|---|
| Run | [`20261110_191135`](telemetry_correlation_report/CoreUltra7_366H/20261110_191135/) | [`20261110_025123`](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux/tree/main/reports/telemetry_correlation_report/CoreUltra7_366H/20261110_025123) |
| Configuration | `UltimatePerformance` power plan | `performance` profile, `powersave` governor |
| PassMark | PerformanceTest **11.1** | PerformanceTest Linux **11.0.1004** (from its topology-probe log) |
| Iterations / processes | 1 / 16 | 1 / 16 |
| Duration setting | Short | Short |
| Suite run | Run All Tests (CPU, 2D, 3D, Memory, Disk) | `-r All` (CPU, Memory) |

Both are the best score of their OS at the same PassMark major version (11.x)
and iteration count. Windows `HighPerformance` (11.1) is within 0.1% of
`UltimatePerformance`, so the choice between them does not change the result.

## Best score

| Score | Windows | Ubuntu | Ubuntu vs. Windows |
|---|---:|---:|---:|
| CPU Mark | 33,864.4 | 32,253.0 | -4.76% |
| Memory Mark | 3,724.6 (3,727.0 with `HighPerformance`) | 3,759.0 | +0.9% |

Other results for context (not like-for-like):

- Windows on PassMark 10.2 scored up to 34,355.6 CPU Mark (`UltimatePerformance`),
  so the CPU Mark gap is 6.1% against 10.2 and 4.8% against 11.1; part of it is
  the PassMark version.
- Ubuntu's best Memory Mark was 3,790 (three-iteration run, Nov 4), +1.7% vs.
  Windows' best 3,727.

## CPU sub-tests

Order is each OS's run order. Ubuntu's is from its results file and console log.
Windows' is the exported listing order, which EMON supports (Single Threaded
runs last).

| Test | Windows order | Ubuntu order | Windows | Ubuntu | Ubuntu vs. Windows |
|---|---:|---:|---:|---:|---:|
| Integer Math | 1 | 1 | 86,973 | 90,872 | +4.5% |
| Floating Point | 2 | 2 | 112,869 | 108,925 | -3.5% |
| Prime Numbers | 3 | 3 | 366.1 | 271 | -26.0% |
| SSE (matrix) | 4 | 9 | 32,024 | 17,666 | -44.8% |
| Compression | 5 | 6 | 291,922 | 277,356 | -5.0% |
| Encryption | 6 | 5 | 25,358 | 24,925 | -1.7% |
| Physics | 7 | 8 | 2,791 | 3,271 | +17.2% |
| Sorting | 8 | 4 | 36,606 | 47,310 | +29.2% |
| Single Threaded | 9 | 7 | 4,466 | 4,456 | -0.2% |
| **CPU Mark** | | | **33,864** | **32,253** | **-4.76%** |

## SKU core topology

Intel Core Ultra 7 366H (Panther Lake): 16 cores / 16 threads, no Hyper-Threading
(1 thread per core), as reported by EMON.

| Core type | Count | Architecture |
|---|---:|---|
| P-core | 4 | Cougar Cove |
| E-core | 8 | Darkmont |
| LPE-core (low-power E) | 4 | Darkmont |
| **Total** | **16** | |

The Ubuntu PassMark probe reports 4 logical P-cores and 12 logical E-cores
(the 8 E and 4 LPE cores counted together) and sets `logical_per_pcore = 2`,
so it computes 4/2 + 12 = **14 cores** and runs Prime Numbers on 14 threads
instead of 16. The OS and EMON still report all 16 cores online.

## Reading the result

- Windows' CPU Mark is about 4.8% higher. Memory Mark is about equal (within 1%).
- Single Threaded, Encryption and Compression are within 5% of each other.
- **Prime Numbers** is 26% lower on Ubuntu. It runs on 14 of 16 cores there
  (see topology above), but that is only 12.5% fewer threads, so thread count
  alone does not explain a 26% gap. Cause not established.
- **SSE** (-44.8%) and **Sorting** (+29.2%) differ most and swap positions in
  the run order, so run order may contribute (for example, through where each
  test falls relative to power-limit behavior). This is a hypothesis only.
  Neither is a proven cause.

## Limits

- One run per OS; no repeatability estimate. Ubuntu's repeated three-iteration
  runs agree within about 0.4%.
- The PassMark builds are the same major version but not identical
  (Windows 11.1, Linux 11.0.1004), and Windows is a GUI build while Linux is the CLI.
- Sub-test names match but equivalence of the work done is not audited.
- Windows run order is inferred (listing order plus EMON), not recorded.
- Ubuntu's PassMark version is recorded for `20261110_025123` only; other Ubuntu
  runs do not archive it.

Sources: [Windows scores](telemetry_correlation_report/CoreUltra7_366H/20261110_191135/PassMark_PerfRes.txt),
[Ubuntu scores](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux/blob/main/reports/telemetry_correlation_report/CoreUltra7_366H/20261110_025123/results_console_all.yml),
[Ubuntu version log](https://github.com/KhairulIzwan/passmark-socwatch-emon-linux/blob/main/reports/telemetry_correlation_report/CoreUltra7_366H/20261110_025123/topology_probe/PerformancetestDebug.log).
