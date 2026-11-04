"""
analyze_run.py
Parses PassMark + SoCWatch + EMON results from a CombinedTest_Results run folder
and produces telemetry plots.

Usage:
    python analyze_run.py "C:\\CombinedTest_Results\\20261012_210558"
"""
import sys
import re
import csv
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_FREQ_GHZ = 2.9  # fallback only - real value is auto-detected per run from socwatch.csv
N_CORES = 16  # fallback only - real value is auto-detected per run from socwatch.csv


def detect_base_freq_ghz(socwatch_path: Path) -> float:
    """Reads 'CPU Base Operating Frequency (MHz): ####' from socwatch.csv; falls back to
    BASE_FREQ_GHZ if not found (e.g. older socwatch.csv without that header line)."""
    try:
        with open(socwatch_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        m = re.search(r"CPU Base Operating Frequency \(MHz\):\s*([\d.]+)", text)
        if m:
            return float(m.group(1)) / 1000.0
    except (OSError, FileNotFoundError):
        pass
    return BASE_FREQ_GHZ


def detect_n_cores(socwatch_path: Path) -> int:
    """Counts 'Package_0/Core_N =' lines in socwatch.csv to get the real logical-CPU count;
    falls back to N_CORES if not found."""
    try:
        with open(socwatch_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        cores = set(re.findall(r"Package_\d+/Core_(\d+)\s*=", text))
        if cores:
            return len(cores)
    except (OSError, FileNotFoundError):
        pass
    return N_CORES


def parse_emon(emon_path: Path, n_cores: int = N_CORES, base_freq_ghz: float = BASE_FREQ_GHZ) -> pd.DataFrame:
    """Parse emon.csv block-sampled counters into a tidy per-sample, per-core DataFrame."""
    with open(emon_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    blocks = []
    current = {}
    for line in lines:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        if line.startswith("=========="):
            if current:
                blocks.append(current)
            current = {}
            continue
        if line.startswith("Version Info"):
            continue
        parts = [p.strip().replace(",", "") for p in line.split("\t") if p.strip() != ""]
        if len(parts) < 2:
            continue
        name = parts[0]
        try:
            vals = [float(v) for v in parts[1:]]
        except ValueError:
            continue
        current[name] = vals

    if current:
        blocks.append(current)

    records = []
    for i, block in enumerate(blocks):
        interval_ref = None
        inst = block.get("INST_RETIRED.ANY")
        reftsc = block.get("CPU_CLK_UNHALTED.REF_TSC")
        miss = block.get("LONGEST_LAT_CACHE.MISS")
        if not inst or not reftsc:
            continue
        interval_ref = inst[0]  # column 1 = interval TSC marker (same for all rows)
        for core in range(n_cores):
            col = core + 1
            if col >= len(inst):
                break
            inst_v = inst[col]
            ref_v = reftsc[col]
            miss_v = miss[col] if miss and col < len(miss) else float("nan")
            freq_ghz = (ref_v / interval_ref) * base_freq_ghz if interval_ref else float("nan")
            ipc = inst_v / ref_v if ref_v else float("nan")
            miss_rate = (miss_v / inst_v * 1000) if inst_v else float("nan")  # misses per 1k instr
            records.append({
                "sample": i,
                "core": core,
                "inst_retired": inst_v,
                "ref_tsc": ref_v,
                "cache_miss": miss_v,
                "freq_ghz": freq_ghz,
                "ipc": ipc,
                "cache_miss_per_kinst": miss_rate,
            })
    return pd.DataFrame(records)


def parse_socwatch_table(lines, header_idx):
    """Parse a simple 'C-State, col1, col2, ...' table starting at header_idx."""
    header = [h.strip() for h in lines[header_idx].split(",")]
    data = []
    i = header_idx + 1
    while i < len(lines) and lines[i].strip() and "," in lines[i]:
        parts = [p.strip() for p in lines[i].split(",")]
        if len(parts) == len(header):
            data.append(parts)
        i += 1
    df = pd.DataFrame(data, columns=header)
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def parse_socwatch_summaries(socwatch_path: Path):
    with open(socwatch_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    lines = [l.rstrip("\n") for l in lines]

    tables = {}
    for idx, line in enumerate(lines):
        if line.startswith("C-State, CPU/Package_0 Residency"):
            # Determine which summary this belongs to by looking back for nearest title
            title = next((lines[j] for j in range(idx - 1, max(idx - 6, 0), -1) if "Summary" in lines[j]), f"table_{idx}")
            tables[title] = parse_socwatch_table(lines, idx)
    return tables


def parse_passmark(passmark_path: Path):
    scores = {}
    with open(passmark_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r"^(.*?)\s*:\s*([\d.]+)\s*\((\d+)%\)\s*$", line.strip())
            if m:
                scores[m.group(1).strip()] = {"value": float(m.group(2)), "percentile": int(m.group(3))}
    return scores


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_run.py <run_folder>")
        sys.exit(1)

    run_dir = Path(sys.argv[1])
    out_dir = run_dir / "analysis"
    out_dir.mkdir(exist_ok=True)

    emon_path = run_dir / "emon.csv"
    socwatch_path = run_dir / "socwatch.csv"
    passmark_path = run_dir / "PassMark_PerfRes.txt"

    n_cores = detect_n_cores(socwatch_path)
    base_freq_ghz = detect_base_freq_ghz(socwatch_path)
    print(f"Detected SKU config: n_cores={n_cores}, base_freq_ghz={base_freq_ghz}")

    print(f"Parsing emon.csv from {emon_path} ...")
    emon_df = parse_emon(emon_path, n_cores=n_cores, base_freq_ghz=base_freq_ghz)
    emon_df.to_csv(out_dir / "emon_timeseries_tidy.csv", index=False)
    print(f"  -> {len(emon_df)} rows, {emon_df['sample'].nunique()} samples, "
          f"{emon_df['core'].nunique()} cores")

    print("Parsing socwatch.csv summaries ...")
    soc_tables = parse_socwatch_summaries(socwatch_path)
    for name, df in soc_tables.items():
        print(f"  Found table: {name} ({df.shape[0]} rows)")

    print("Parsing PassMark score ...")
    scores = parse_passmark(passmark_path)
    for k, v in scores.items():
        print(f"  {k}: {v['value']} ({v['percentile']}%)")

    # ---------- Plot 1: Average frequency across all cores over time ----------
    avg_freq = emon_df.groupby("sample")["freq_ghz"].mean()
    avg_ipc = emon_df.groupby("sample")["ipc"].mean()
    avg_miss = emon_df.groupby("sample")["cache_miss_per_kinst"].mean()

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    axes[0].plot(avg_freq.index, avg_freq.values, color="tab:blue")
    axes[0].set_ylabel("Avg Freq (GHz)")
    axes[0].set_title(f"Average CPU Frequency Across {emon_df['core'].nunique()} Logical CPUs Over Time")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(avg_ipc.index, avg_ipc.values, color="tab:green")
    axes[1].set_ylabel("Avg IPC")
    axes[1].set_title("Average IPC (Instructions per Cycle) Over Time")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(avg_miss.index, avg_miss.values, color="tab:red")
    axes[2].set_ylabel("LLC Misses / 1k Instr")
    axes[2].set_xlabel("Sample # (~1 sample/sec)")
    axes[2].set_title("Average Last-Level Cache Miss Rate Over Time")
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "01_timeseries_overview.png", dpi=150)
    plt.close(fig)

    # ---------- Plot 2: Per-core frequency heatmap ----------
    pivot = emon_df.pivot(index="core", columns="sample", values="freq_ghz")
    fig, ax = plt.subplots(figsize=(14, 5))
    im = ax.imshow(pivot.values, aspect="auto", cmap="viridis",
                    extent=[0, pivot.shape[1], pivot.shape[0], 0])
    ax.set_xlabel("Sample # (~1 sample/sec)")
    ax.set_ylabel("Logical CPU")
    ax.set_title("Per-Core Frequency Heatmap (GHz)")
    fig.colorbar(im, ax=ax, label="GHz")
    fig.tight_layout()
    fig.savefig(out_dir / "02_per_core_freq_heatmap.png", dpi=150)
    plt.close(fig)

    # ---------- Plot 3: C-State residency bar charts ----------
    n_tables = len(soc_tables)
    if n_tables:
        fig, axes = plt.subplots(n_tables, 1, figsize=(10, 4 * n_tables))
        if n_tables == 1:
            axes = [axes]
        for ax, (name, df) in zip(axes, soc_tables.items()):
            pct_cols = [c for c in df.columns if "(%)" in c]
            if not pct_cols or df.empty:
                continue
            df.set_index(df.columns[0])[pct_cols].plot(kind="bar", ax=ax)
            ax.set_title(name)
            ax.set_ylabel("Residency (%)")
            ax.tick_params(axis="x", rotation=0)
        fig.tight_layout()
        fig.savefig(out_dir / "03_cstate_residency.png", dpi=150)
        plt.close(fig)

    # ---------- Plot 4: PassMark score summary bar chart ----------
    if scores:
        names = list(scores.keys())
        pct = [scores[k]["percentile"] for k in names]
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.barh(names, pct, color="tab:purple")
        ax.set_xlabel("Percentile vs PassMark baseline (%)")
        ax.set_title("PassMark Sub-Test Percentiles")
        ax.invert_yaxis()
        fig.tight_layout()
        fig.savefig(out_dir / "04_passmark_percentiles.png", dpi=150)
        plt.close(fig)

    print(f"\nDone. Plots and tidy CSV written to: {out_dir}")


if __name__ == "__main__":
    main()
