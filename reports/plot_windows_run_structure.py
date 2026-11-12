"""EMON activity of the two Windows CPU+Memory-only runs, to show run structure.

Top: CPU > All then Memory (back to back). Bottom: each CPU test started
individually in Ubuntu's order (-CpuOrder Ubuntu), then Memory. Instructions
retired per second, stacked by core type (P = cores 0-3, E = 4-11,
LPE = 12-15, inferred from the IPC pattern). "Active" seconds are those with
more than 5 billion instructions retired across all cores.

Usage: python plot_windows_run_structure.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = HERE / "cpu_memory_only/CoreUltra7_366H"
RUNS = [
    ("CPU > All, then Memory (20261111_191425): CPU Mark 33,694, 22.1 W, PBM-PL1 12.9%",
     BASE / "20261111_191425/analysis/emon_timeseries_tidy.csv"),
    ("CPU tests one at a time in Ubuntu's order, then Memory (20261111_193915): "
     "CPU Mark 38,839, 17.1 W, PBM-PL1 0.7%",
     BASE / "20261111_193915/analysis/emon_timeseries_tidy.csv"),
]
GROUPS = {"P (0-3)": range(0, 4), "E (4-11)": range(4, 12), "LPE (12-15)": range(12, 16)}
COLORS = {"P (0-3)": "#1f77b4", "E (4-11)": "#ff7f0e", "LPE (12-15)": "#2ca02c"}


def load(path):
    d = pd.read_csv(path)
    d["grp"] = d["core"].map({c: g for g, r in GROUPS.items() for c in r})
    inst = d.pivot_table(index="sample", columns="grp", values="inst_retired", aggfunc="sum") / 1e9
    return inst[list(GROUPS)]


def main():
    fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True, sharey=True)
    for ax, (title, path) in zip(axes, RUNS):
        inst = load(path)
        total = inst.sum(axis=1)
        active = int((total > 5).sum())
        ax.stackplot(inst.index, [inst[g] for g in GROUPS], labels=list(GROUPS),
                     colors=[COLORS[g] for g in GROUPS], alpha=0.85)
        ax.set_title(f"{title}\n{len(inst)} s captured, {active} s active "
                     f"({100 * active / len(inst):.0f}%)", fontsize=10, loc="left")
        ax.set_ylabel("Instructions retired (B/s)")
        ax.grid(alpha=0.3)
    axes[0].legend(loc="upper right", ncol=3, fontsize=8)
    axes[1].set_xlabel("EMON sample (s)")
    fig.suptitle("Windows run structure: idle gaps between individually started tests "
                 "(Core Ultra 7 366H)", fontsize=12)
    fig.tight_layout()
    out = HERE / "windows_run_structure.png"
    fig.savefig(out, dpi=130)
    print("wrote", out)


if __name__ == "__main__":
    main()
