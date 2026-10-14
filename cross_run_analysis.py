"""
cross_run_analysis.py
Aggregates PassMark scores + SoCWatch/EMON telemetry across every run folder under
C:\\CombinedTest_Results, computes correlations between benchmark scores and
telemetry, and emits:
  - combined_runs.csv              (one row per run: scores + telemetry)
  - correlation_matrix.csv
  - plots/*.png                    (heatmap + top scatter plots)
  - TELEMETRY_CORRELATION_REPORT.md

Usage:
    python cross_run_analysis.py "C:\\CombinedTest_Results"
"""
import sys
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import pearsonr

sys.path.insert(0, str(Path(__file__).parent))
from analyze_run import parse_emon, parse_passmark  # noqa: E402

N_CORES = 16

SCORE_COLS_OF_INTEREST = [
    "PassMark Rating (Composite average)",
    "CPU Mark (Composite average)",
    "Memory Mark (Composite average)",
    "Disk Mark (Composite average)",
    "2D Graphics Mark (Composite average)",
    "3D Graphics Mark (Composite average)",
]

TELEMETRY_COLS_OF_INTEREST = [
    "avg_pkg_power_mW",
    "avg_active_freq_mhz",
    "pkg_c0_pct",
    "avg_ipc",
    "avg_cache_miss_per_kinst",
    "collection_duration_sec",
]


def parse_socwatch_summary(socwatch_path: Path) -> dict:
    with open(socwatch_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    lines = text.splitlines()
    out = {}

    m = re.search(r"Collection duration \(sec\):\s*([\d.]+)", text)
    if m:
        out["collection_duration_sec"] = float(m.group(1))

    # Package Power Summary: Average Rate and Total
    m = re.search(r"CPU/Package_0,\s*Power\s*,\s*([\d.]+)\s*,", text)
    if m:
        out["avg_pkg_power_mW"] = float(m.group(1))

    # CPU P-State Average Frequency (excluding CPU idle time) - average across threads
    for i, line in enumerate(lines):
        if line.strip().startswith("CPU P-State Average Frequency"):
            freqs = []
            j = i + 3  # skip title-adjacent header line + column header + dashed separator
            while j < len(lines) and "," in lines[j] and "Thread" in lines[j]:
                parts = lines[j].split(",")
                try:
                    freqs.append(float(parts[1].strip()))
                except (ValueError, IndexError):
                    pass
                j += 1
            if freqs:
                out["avg_active_freq_mhz"] = sum(freqs) / len(freqs)
            break

    # Package C-State (OS) Summary: Residency -> ACPI C0 %
    for i, line in enumerate(lines):
        if line.strip().startswith("C-State, CPU/Package_0 Residency") and \
           "Package C-State (OS)" in "\n".join(lines[max(0, i - 6):i]):
            j = i + 1
            while j < len(lines) and lines[j].strip():
                parts = [p.strip() for p in lines[j].split(",")]
                if len(parts) >= 2 and parts[0] == "ACPI C0":
                    try:
                        out["pkg_c0_pct"] = float(parts[1])
                    except ValueError:
                        pass
                j += 1
            break

    return out


def parse_emon_summary(emon_path: Path) -> dict:
    df = parse_emon(emon_path)
    if df.empty:
        return {}
    return {
        "avg_ipc": df["ipc"].mean(),
        "avg_cache_miss_per_kinst": df["cache_miss_per_kinst"].mean(),
        "avg_freq_ghz_all_samples": df["freq_ghz"].mean(),
    }


def parse_system_info(sysinfo_path: Path) -> dict:
    if not sysinfo_path.exists():
        return {}
    text = sysinfo_path.read_text(encoding="utf-8", errors="ignore")
    out = {}
    patterns = {
        "cpu_model": r"Model:\s*(.+)",
        "cores_threads": r"Cores/Threads:\s*(.+)",
        "memory_total": r"Total installed:\s*(.+)",
        "bios_version": r"Version:\s*([^\|]+)",
        "os": r"Operating System\s*--\s*\n(.+)",
        "gpu": r"GPU\(s\)\s*--\s*\n(.+)",
        "power_plan_applied": r"Applied for this run:\s*(\S+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            out[key] = m.group(1).strip()
    return out


def collect_runs(root: Path) -> tuple[pd.DataFrame, dict]:
    rows = []
    sys_info = {}
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir() or not re.match(r"\d{8}_\d{6}", run_dir.name):
            continue
        pm_path = run_dir / "PassMark_PerfRes.txt"
        sw_path = run_dir / "socwatch.csv"
        em_path = run_dir / "emon.csv"
        si_path = run_dir / "system_info.txt"

        if not pm_path.exists() or not sw_path.exists():
            print(f"Skipping {run_dir.name}: missing PassMark or socwatch data (run may be in progress)")
            continue

        row = {"run": run_dir.name}
        scores = parse_passmark(pm_path)
        for k, v in scores.items():
            row[k] = v["value"]

        row.update(parse_socwatch_summary(sw_path))

        if em_path.exists():
            row.update(parse_emon_summary(em_path))

        run_sys_info = parse_system_info(si_path)
        if run_sys_info:
            row["cpu_model"] = run_sys_info.get("cpu_model")
            row["power_plan"] = run_sys_info.get("power_plan_applied")
            if not sys_info:
                sys_info = run_sys_info

        rows.append(row)

    return pd.DataFrame(rows).set_index("run"), sys_info


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\Users\Local_Admin\Desktop\passmark-socwatch-emon-win\Results")
    out_dir = root / "cross_run_analysis"
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    df, sys_info = collect_runs(root)
    df.to_csv(out_dir / "combined_runs.csv")
    print(f"Collected {len(df)} runs -> {out_dir / 'combined_runs.csv'}")

    score_cols = [c for c in SCORE_COLS_OF_INTEREST if c in df.columns]
    tel_cols = [c for c in TELEMETRY_COLS_OF_INTEREST if c in df.columns]

    sub = df[score_cols + tel_cols].dropna(how="all")
    corr = sub.corr(method="pearson")
    corr.to_csv(out_dir / "correlation_matrix.csv")

    # p-values for score x telemetry pairs
    pval_rows = []
    for s in score_cols:
        for t in tel_cols:
            paired = df[[s, t]].dropna()
            if len(paired) < 3:
                continue
            r, p = pearsonr(paired[s], paired[t])
            pval_rows.append({"score": s, "telemetry": t, "r": r, "p_value": p, "n": len(paired)})
    pvals = pd.DataFrame(pval_rows).sort_values("r", key=lambda s: s.abs(), ascending=False) \
        if pval_rows else pd.DataFrame(columns=["score", "telemetry", "r", "p_value", "n"])
    pvals.to_csv(out_dir / "score_telemetry_pairs.csv", index=False)

    scatter_files = []
    bar_files = []
    if len(df) >= 3:
        # ---- Heatmap ----
        fig, ax = plt.subplots(figsize=(max(8, len(corr) * 0.9), max(6, len(corr) * 0.7)))
        im = ax.imshow(corr.values, cmap="coolwarm", vmin=-1, vmax=1)
        ax.set_xticks(range(len(corr.columns)))
        ax.set_xticklabels(corr.columns, rotation=60, ha="right", fontsize=8)
        ax.set_yticks(range(len(corr.index)))
        ax.set_yticklabels(corr.index, fontsize=8)
        for i in range(len(corr.index)):
            for j in range(len(corr.columns)):
                val = corr.values[i, j]
                if not np.isnan(val):
                    ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                             color="white" if abs(val) > 0.6 else "black", fontsize=7)
        fig.colorbar(im, ax=ax, label="Pearson r")
        ax.set_title(f"Score vs Telemetry Correlation (n={len(df)} runs)")
        fig.tight_layout()
        fig.savefig(plots_dir / "correlation_heatmap.png", dpi=150)
        plt.close(fig)

        # ---- Top scatter plots ----
        top_pairs = pvals.head(6)
        for _, prow in top_pairs.iterrows():
            s, t, r, p, n = prow["score"], prow["telemetry"], prow["r"], prow["p_value"], prow["n"]
            paired = df[[s, t]].dropna()
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.scatter(paired[t], paired[s], color="tab:blue")
            if len(paired) >= 2:
                z = np.polyfit(paired[t], paired[s], 1)
                xs = np.linspace(paired[t].min(), paired[t].max(), 50)
                ax.plot(xs, np.polyval(z, xs), color="tab:red", linestyle="--")
            ax.set_xlabel(t)
            ax.set_ylabel(s)
            ax.set_title(f"r={r:.2f}, p={p:.3f}, n={int(n)}")
            fig.tight_layout()
            fname = f"scatter_{re.sub(r'[^A-Za-z0-9]+', '_', s)[:30]}_vs_{re.sub(r'[^A-Za-z0-9]+', '_', t)[:30]}.png"
            fig.savefig(plots_dir / fname, dpi=150)
            plt.close(fig)
            scatter_files.append((s, t, r, p, n, fname))
    else:
        # Not enough runs for correlation - produce simple per-run/per-plan comparison bar charts instead.
        def _bar_grid(cols, fname, suptitle):
            if not cols:
                return None
            ncols = 3
            nrows = int(np.ceil(len(cols) / ncols))
            fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows), squeeze=False)
            labels = [f"{idx}\n({df.loc[idx, 'power_plan']})" if "power_plan" in df.columns
                      else str(idx) for idx in df.index]
            colors = plt.cm.tab10.colors
            for i, col in enumerate(cols):
                ax = axes[i // ncols][i % ncols]
                ax.bar(labels, df[col].values, color=[colors[j % 10] for j in range(len(df))])
                ax.set_title(col, fontsize=9)
                ax.tick_params(axis="x", labelsize=7, rotation=0)
            for i in range(len(cols), nrows * ncols):
                axes[i // ncols][i % ncols].axis("off")
            fig.suptitle(suptitle)
            fig.tight_layout()
            fig.savefig(plots_dir / fname, dpi=150)
            plt.close(fig)
            return fname

        bar_files = []
        f1 = _bar_grid(score_cols, "bars_scores_by_run.png",
                        f"PassMark Scores by Run (n={len(df)}, not enough for correlation)")
        f2 = _bar_grid(tel_cols, "bars_telemetry_by_run.png",
                        f"Telemetry by Run (n={len(df)}, not enough for correlation)")
        for f in (f1, f2):
            if f:
                bar_files.append(f)

    # ---- Markdown report ----
    md = []
    md.append("# Telemetry ↔ PassMark Score Correlation Report\n")
    md.append(f"Generated from `{root}` — {len(df)} runs with usable data "
              f"(PassMark + SoCWatch{', EMON' if 'avg_ipc' in df.columns else ''}).\n")

    if sys_info:
        md.append("## Test-Bed Configuration\n")
        label_map = {
            "cpu_model": "CPU",
            "cores_threads": "Cores/Threads",
            "memory_total": "Memory",
            "bios_version": "BIOS",
            "gpu": "GPU",
        }
        for key, label in label_map.items():
            if sys_info.get(key):
                md.append(f"- **{label}**: {sys_info[key]}\n")
        n_plans = df["power_plan"].nunique() if "power_plan" in df.columns else 0
        if n_plans > 1:
            md.append(f"- **Power plan**: varies per run ({n_plans} plans tested: "
                       f"{', '.join(sorted(df['power_plan'].dropna().unique()))}) — see breakdown below.\n")
        elif n_plans == 1:
            md.append(f"- **Power plan (during run)**: {df['power_plan'].dropna().iloc[0]}\n")
        md.append("\n")

    md.append("## Methodology\n")
    md.append(
        "- **PassMark** supplies one composite/sub-test score per run (`PassMark_PerfRes.txt`), "
        "not a time series.\n"
        "- **SoCWatch** (`socwatch.csv`) supplies whole-run summary telemetry: average package "
        "power (mW), average active CPU frequency excluding idle time (MHz), and package C-state "
        "residency (% time in ACPI C0 = active).\n"
        "- **EMON** (`emon.csv`), where present, supplies ~1-sample/sec counters across the full "
        "run; these were averaged into run-level IPC and last-level-cache-miss-rate metrics.\n"
        "- Each **run becomes one observation**; correlation (Pearson r) is computed **across runs** "
        "between score metrics and telemetry metrics — this is the only valid level for score "
        "correlation since PassMark itself has no internal time resolution.\n"
        "- ⚠️ **Caveat**: with "
        f"**n={len(df)}** runs on a single SKU/system (one run per power plan), these are "
        "exploratory correlations, not statistically robust conclusions:\n"
        "  - Each PassMark score is itself already an average across the run's internal "
        "**3 iterations**, so the *score* values have reasonably low pure benchmark-noise.\n"
        "  - However, **telemetry (SoCWatch/EMON) was captured once per run**, not separately "
        "per iteration — so we don't know iteration-to-iteration telemetry variance (e.g., "
        "thermal ramp across the 3 iterations), and runs were executed back-to-back without "
        "controlling for thermal/background-state carryover between power-plan switches.\n"
        "  - With only n=4 distinct conditions, a single atypical plan can dominate the fit — "
        "p<0.05 here should be read as a credible **directional** signal worth acting on, "
        "not a finalized regression. Confirming with 1-2 repeat runs per plan (especially for "
        "any plan that looks like an outlier) would turn this from directional into robust.\n"
    )

    md.append("## Per-Run Summary Table\n")
    display_cols = (["power_plan"] if "power_plan" in df.columns else []) + score_cols + tel_cols
    md.append(df[display_cols].round(2).to_markdown())
    md.append("\n")

    plot_titles = {
        "01_timeseries_overview.png": "Timeseries overview (freq / IPC / cache-miss)",
        "02_per_core_freq_heatmap.png": "Per-core frequency heatmap",
        "03_cstate_residency.png": "C-state residency",
        "04_passmark_percentiles.png": "PassMark sub-test percentiles",
    }
    runs_with_plots = [idx for idx in df.index if (root / idx / "analysis").exists()]
    if runs_with_plots:
        md.append("## Per-Run Detailed Plots (Side-by-Side by Plot Type)\n")
        md.append(
            "Each completed run also has its own 4-plot deep-dive (generated by "
            "`analyze_run.py` / `analyze_all.py`), covering within-run telemetry trends "
            "that the cross-run tables above don't show. Grouped here by plot type so runs/"
            "power plans can be compared side by side; click/open an image for full resolution.\n\n"
        )
        thumb_width = 320
        for fname, title in plot_titles.items():
            available = [idx for idx in runs_with_plots if (root / idx / "analysis" / fname).exists()]
            if not available:
                continue
            md.append(f"### {title}\n\n")
            md.append("<table><tr>\n")
            for idx in available:
                plan = df.loc[idx, "power_plan"] if "power_plan" in df.columns else ""
                caption = f"{idx}<br/>{plan}" if plan else idx
                md.append(
                    f'<td align="center"><b>{caption}</b><br/>'
                    f'<img src="{idx}/analysis/{fname}" width="{thumb_width}"/></td>\n'
                )
            md.append("</tr></table>\n\n")

    if "power_plan" in df.columns and df["power_plan"].nunique() > 1:
        md.append("## Comparison by Power Plan\n")
        md.append(
            "Grouped mean per power plan (n = number of runs in that group). With few runs per "
            "group this is **descriptive, not statistically significant** — treat as a starting "
            "point for which plan looks favorable per metric, then confirm with repeats.\n\n"
        )
        grp = df.groupby("power_plan")[score_cols + tel_cols].agg(["mean", "count"])
        # flatten and keep count only once (same for all cols per group) for readability
        counts = df.groupby("power_plan").size().rename("n")
        means = df.groupby("power_plan")[score_cols + tel_cols].mean().round(2)
        means.insert(0, "n", counts)
        md.append(means.to_markdown())
        md.append("\n")

    if len(df) >= 2:
        md.append("## Run-to-Run Repeatability (All Runs, Mixed Config)\n")
        md.append(
            "Mean / standard deviation / coefficient of variation (CoV%) across **all** collected "
            "runs regardless of power plan — inflated by any power-plan differences above, so "
            "use the per-plan breakdown for a cleaner repeatability read once you have ≥2 runs "
            "per plan.\n\n"
        )
        rep = pd.DataFrame({
            "mean": df[display_cols[1:] if "power_plan" in df.columns else display_cols].mean(),
            "std": df[display_cols[1:] if "power_plan" in df.columns else display_cols].std(),
        })
        rep["cov_pct"] = (rep["std"] / rep["mean"] * 100).round(2)
        md.append(rep.round(3).to_markdown())
        md.append("\n")

    if len(df) < 3:
        md.append(
            "\n> ℹ️ Fewer than 3 complete runs are available, so Pearson correlation "
            "(needs variance across ≥3 points) is skipped below. Add more repeat runs to "
            "populate the correlation matrix and scatter plots. In the meantime, here are "
            "simple per-run comparison charts (no statistics implied, just the table above "
            "plotted).\n\n"
        )
        for fname in bar_files:
            md.append(f"![{fname}](cross_run_analysis/plots/{fname})\n\n")
    else:
        md.append("## Correlation Matrix\n")
        md.append("![Correlation Heatmap](cross_run_analysis/plots/correlation_heatmap.png)\n")
        md.append(corr.round(2).to_markdown())
        md.append("\n")

        md.append("## Strongest Score ↔ Telemetry Relationships\n")
        md.append("| Score | Telemetry | r | p-value | n |\n|---|---|---|---|---|\n")
        for _, prow in pvals.head(10).iterrows():
            md.append(f"| {prow['score']} | {prow['telemetry']} | {prow['r']:.2f} | "
                       f"{prow['p_value']:.3f} | {int(prow['n'])} |\n")
        md.append("\n")

        md.append("## Scatter Plots (Top 6 by |r|)\n")
        for s, t, r, p, n, fname in scatter_files:
            md.append(f"### {s} vs {t} (r={r:.2f}, p={p:.3f}, n={int(n)})\n")
            md.append(f"![{s} vs {t}](cross_run_analysis/plots/{fname})\n\n")

    md.append("## How to Read This for SKU/Workload Behavior\n")
    md.append(
        "- A **positive r between a score and average package power/frequency** suggests the "
        "workload scales with power/turbo headroom — i.e. the SKU is power- or frequency-limited "
        "for that sub-test, and raising power limits (PL1/PL2) or cooling should move the score.\n"
        "- A **flat/near-zero r** suggests the sub-test is bound by something else telemetry here "
        "doesn't capture well (e.g., GPU-bound DirectX tests vs. CPU-only telemetry, disk I/O, "
        "memory latency) — look at `2D/3D Graphics Mark` vs CPU telemetry as the expected example "
        "of weak correlation.\n"
        "- A **negative r with C0 residency** can indicate the benchmark finishes faster (less busy "
        "time / score) at higher scores, or that runs with more idle/background interference score "
        "lower — inspect the specific run rows, don't over-interpret from r alone.\n"
        "- To get statistically solid conclusions: run more repeats per configuration, vary one "
        "knob at a time (e.g., PL1/PL2, frequency cap), and keep workload identical across runs.\n"
    )

    report_path = root / "TELEMETRY_CORRELATION_REPORT.md"
    report_path.write_text("\n".join(md), encoding="utf-8")
    print(f"\nReport written to: {report_path}")
    print(f"Supporting data/plots in: {out_dir}")


if __name__ == "__main__":
    main()
