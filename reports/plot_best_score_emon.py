"""Per-second EMON view of the best Windows and best Ubuntu CPU Mark runs.

Test windows are approximate: they are read from activity transitions in the
EMON instruction counts, not recorded by PassMark. Windows order is inferred
from the PassMark_PerfRes.txt listing; Ubuntu order is from the PassMark log.

Usage: python plot_best_score_emon.py [path-to-passmark-socwatch-emon-linux]
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
LINUX_REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[1] / "passmark-socwatch-emon-linux"
SKU = "telemetry_correlation_report/CoreUltra7_366H"
WIN_CSV = HERE / SKU / "20261110_191135/analysis/emon_timeseries_tidy.csv"
UBU_CSV = LINUX_REPO / "reports" / SKU / "20261110_025123/analysis/emon_timeseries_tidy.csv"

# (name, start_s, end_s) in EMON sample seconds, end exclusive
WIN_TESTS = [("Integer", 1, 5), ("Float", 5, 9), ("Prime", 9, 13), ("SSE", 13, 18),
             ("Compress", 18, 23), ("Encrypt", 23, 28), ("Physics", 28, 32),
             ("Sorting", 32, 41), ("Single", 41, 52)]
UBU_TESTS = [("Integer", 4, 8), ("Float", 8, 12), ("Prime", 12, 16), ("Sorting", 16, 20),
             ("Encrypt", 20, 24), ("Compress", 24, 32), ("Single", 33, 37),
             ("Physics", 37, 41), ("SSE", 41, 51)]
GROUPS = {"P (0-3)": range(0, 4), "E (4-11)": range(4, 12), "LPE (12-15)": range(12, 16)}
COLORS = {"P (0-3)": "#1f77b4", "E (4-11)": "#ff7f0e", "LPE (12-15)": "#2ca02c"}


def load(path, t0, t1):
    d = pd.read_csv(path)
    d = d[(d["sample"] >= t0) & (d["sample"] < t1)].copy()
    d["grp"] = d["core"].map({c: g for g, r in GROUPS.items() for c in r})
    inst = d.pivot_table(index="sample", columns="grp", values="inst_retired", aggfunc="sum") / 1e9
    freq = d.pivot_table(index="sample", columns="grp", values="freq_ghz", aggfunc="mean")
    return inst[list(GROUPS)], freq[list(GROUPS)]


def table(inst, freq, tests):
    """Per-test means over busy seconds: P-cores >= 3.5 GHz, no start-of-test
    spike (> 1.8x the window median) and no ramp/tail (< 50% of the busiest second)."""
    rows = []
    for name, a, b in tests:
        if name == "Single":
            continue
        s = [x for x in range(a, b) if x in inst.index and freq.loc[x, "P (0-3)"] >= 3.5]
        tot = inst.loc[s].sum(axis=1)
        s = [x for x in s if tot[x] <= 1.8 * tot.median()]
        tot = inst.loc[s].sum(axis=1)
        s = [x for x in s if tot[x] >= 0.5 * tot.max()]
        p_ipc = (inst.loc[s, "P (0-3)"] / 4 / freq.loc[s, "P (0-3)"]).mean()
        rows.append((name, inst.loc[s].sum(axis=1).mean(), freq.loc[s].mean().mean(), p_ipc, len(s)))
    return pd.DataFrame(rows, columns=["test", "inst_B_per_s", "freq_ghz", "p_ipc", "secs"])


def main():
    runs = [("Windows 11 - PT 11.1 - Ultimate (CPU Mark 33,864)", WIN_CSV, WIN_TESTS, 0, 54),
            ("Ubuntu - PT 11.0.1004 - 1 iteration (CPU Mark 32,253)", UBU_CSV, UBU_TESTS, 3, 53)]
    fig, axes = plt.subplots(2, 2, figsize=(15, 7.5), sharey="row")
    tabs = {}
    for col, (title, path, tests, t0, t1) in enumerate(runs):
        inst, freq = load(path, t0, t1)
        x = inst.index - tests[0][1]
        axes[0, col].stackplot(x, [inst[g] for g in GROUPS], labels=list(GROUPS),
                               colors=[COLORS[g] for g in GROUPS], alpha=0.85)
        for g in GROUPS:
            axes[1, col].plot(x, freq[g], label=g, color=COLORS[g], lw=1.6)
        for i, (name, a, b) in enumerate(tests):
            for ax in axes[:, col]:
                ax.axvspan(a - tests[0][1], b - tests[0][1], color="grey", alpha=0.10 if i % 2 else 0.0)
                ax.axvline(a - tests[0][1], color="grey", lw=0.5)
            axes[0, col].text((a + b) / 2 - tests[0][1], 1.01, name, rotation=45, ha="left",
                              va="bottom", fontsize=8, transform=axes[0, col].get_xaxis_transform())
        axes[0, col].set_title(title, pad=42, fontsize=11)
        axes[1, col].set_xlabel("seconds from first CPU test (approximate windows)")
        tabs[col] = table(inst, freq, tests)
    axes[0, 0].set_ylabel("instructions retired (billions/s)")
    axes[1, 0].set_ylabel("mean core frequency (GHz)")
    axes[0, 0].legend(loc="upper right", fontsize=8)
    axes[1, 0].set_ylim(0, 4.2)
    fig.suptitle("Core Ultra 7 366H - best Windows vs best Ubuntu CPU Mark (EMON, CPU suite only)", y=1.0)
    fig.tight_layout()
    out = HERE / "windows_vs_ubuntu_best_score_emon.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print("wrote", out)
    m = tabs[0].merge(tabs[1], on="test", suffixes=("_win", "_ubu"))
    print(m.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
