"""Package power and instructions retired for the Windows CPU+Memory-only run.

Inputs are the archived files in reports/cpu_memory_only/<SKU>/<run>:
  - analysis/emon_timeseries_tidy.csv  (EMON, 1 s samples)
  - socwatch_pkg_power_trace.csv       (SocWatch package power, about 90 ms samples)
  - socwatch_cpu_pbm_pl1_trace.csv     (SocWatch PBM-PL1 throttle flag)
The SocWatch traces were exported from the raw .etl with:
  socwatch -i <run>\\socwatch -r int -o <prefix>
SocWatch and EMON start a few seconds apart, so the power trace is shifted by the
lag that best correlates it with EMON instructions. Test windows are approximate
(read from EMON activity transitions).

Usage: python plot_windows_power.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RUN = HERE / "cpu_memory_only/CoreUltra7_366H/20261111_191425"

# (name, start_s, end_s) in EMON sample seconds, end exclusive
CPU_TESTS = [("Integer", 1, 5), ("Float", 5, 9), ("Prime", 9, 13), ("SSE", 13, 18),
             ("Compress", 18, 23), ("Encrypt", 23, 28), ("Physics", 28, 32),
             ("Sorting", 32, 40), ("Single", 40, 52)]
MEMORY = ("Memory (all sub-tests)", 56, 101)
GROUPS = {"P (0-3)": range(0, 4), "E (4-11)": range(4, 12), "LPE (12-15)": range(12, 16)}
COLORS = {"P (0-3)": "#1f77b4", "E (4-11)": "#ff7f0e", "LPE (12-15)": "#2ca02c"}


def main():
    e = pd.read_csv(RUN / "analysis/emon_timeseries_tidy.csv")
    e["grp"] = e["core"].map({c: g for g, r in GROUPS.items() for c in r})
    inst = e.pivot_table(index="sample", columns="grp", values="inst_retired", aggfunc="sum")[list(GROUPS)] / 1e9

    p = pd.read_csv(RUN / "socwatch_pkg_power_trace.csv")
    p["t"] = p["ContinuousTime(usec)"] / 1e6
    p["w"] = p["Power(mW)"] / 1000
    pl1 = pd.read_csv(RUN / "socwatch_cpu_pbm_pl1_trace.csv")
    pl1["t"] = pl1["ContinuousTime(usec)"] / 1e6
    pl1["on"] = pl1["PBM-PL1"] != "NotReason"

    sec = np.arange(0, 104)
    pw = p.groupby(np.floor(p["t"]).astype(int))["w"].mean().reindex(sec).interpolate()
    tot = inst.sum(axis=1).reindex(sec).fillna(0)

    def best_lag(a, b):
        """Offset L (EMON s = power s + L) with the best correlation inside EMON seconds a..b."""
        r = {}
        for L in range(0, 9):
            idx = np.arange(a, b)
            y = pw.reindex(idx - L).values
            ok = ~np.isnan(y)
            r[L] = np.corrcoef(tot.reindex(idx).values[ok], y[ok])[0, 1]
        return max(r, key=r.get), r

    lag_cpu, r1 = best_lag(8, 45)
    lag_mem, r2 = best_lag(56, 100)
    print("EMON-to-power offset: CPU phase %d s (r=%.2f), Memory phase %d s (r=%.2f)"
          % (lag_cpu, r1[lag_cpu], lag_mem, r2[lag_mem]))
    for d in (p, pl1):
        d["t_emon"] = d["t"] + np.where(d["t"] + lag_cpu < 54, lag_cpu, lag_mem)

    fig, axes = plt.subplots(2, 1, figsize=(15, 7), sharex=True)
    axes[0].stackplot(inst.index, [inst[g] for g in GROUPS], labels=list(GROUPS),
                      colors=[COLORS[g] for g in GROUPS], alpha=0.85)
    axes[0].set_ylabel("instructions retired (billions/s)")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[1].plot(p["t_emon"], p["w"], color="#d62728", lw=1.2)
    fl = pl1[pl1["on"]]
    axes[1].plot(fl["t_emon"], np.full(len(fl), -2.0), "|", color="black", ms=8,
                 label=f"PBM-PL1 active ({len(fl)} of {len(pl1)} samples, {100 * len(fl) / len(pl1):.1f}%)")
    axes[1].set_ylabel("package power (W)")
    axes[1].set_xlabel("seconds from EMON start (SocWatch starts about %d s later, so its trace is shifted to align)" % lag_cpu)
    axes[1].legend(loc="upper right", fontsize=8)
    axes[1].annotate("Integer ran before\nSocWatch started", xy=(2.5, 3), fontsize=8, ha="center")
    for i, (name, a, b) in enumerate(CPU_TESTS + [MEMORY]):
        for ax in axes:
            ax.axvspan(a, b, color="grey", alpha=0.10 if i % 2 else 0.0)
            ax.axvline(a, color="grey", lw=0.5)
        axes[0].text((a + b) / 2, 1.01, name, rotation=45, ha="left", va="bottom", fontsize=8,
                     transform=axes[0].get_xaxis_transform())
    fig.suptitle("Core Ultra 7 366H - Windows CPU+Memory-only run (PT 11.1, Ultimate Performance, 1 iteration)", y=1.02)
    fig.tight_layout()
    out = HERE / "windows_cpu_memory_power.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print("wrote", out)

    rows = []
    for name, a, b in CPU_TESTS[1:] + [MEMORY]:
        m = (p["t_emon"] >= a) & (p["t_emon"] < b)
        f = (fl["t_emon"] >= a) & (fl["t_emon"] < b)
        n = ((pl1["t_emon"] >= a) & (pl1["t_emon"] < b)).sum()
        rows.append((name, p.loc[m, "w"].mean(), p.loc[m, "w"].max(), 100 * f.sum() / max(n, 1)))
    print(pd.DataFrame(rows, columns=["window", "avg_W", "max_W", "pl1_pct"]).round(1).to_string(index=False))
    cpu = (p["t_emon"] >= 5) & (p["t_emon"] < 52)
    print("CPU-suite (Float..Single) avg W: %.1f; whole capture avg W: %.1f" % (p.loc[cpu, "w"].mean(),
          (p["w"] * p["Duration(ms)"]).sum() / p["Duration(ms)"].sum()))


if __name__ == "__main__":
    main()
