#!/usr/bin/env python3
"""Plot the one-run Windows/Ubuntu PassMark pilot from archived artifacts."""
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml


WINDOWS_RUN = "20261103_231839"
UBUNTU_RUNS = (
    ("performance / powersave", "20261110_025123", "#d66b45"),
    ("balanced / powersave", "20261110_084903", "#c29a2e"),
)
SKU = "CoreUltra7_366H"
WINDOWS_COLOR = "#28708a"


def read_windows_scores(path: Path) -> dict:
    scores = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.fullmatch(r"(.+?)\s*:\s*([0-9.]+)\s*\([0-9]+%\)", line)
        if match:
            scores[match.group(1).strip()] = float(match.group(2))
    return scores


def read_ubuntu_scores(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("Results", {})


def read_socwatch(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    result = {}
    duration = re.search(r"Collection duration \(sec\):\s*([\d.]+)", text)
    power = re.search(r"CPU/Package_0,\s*Power\s*,\s*([\d.]+)\s*,", text)
    result["duration_sec"] = float(duration.group(1)) if duration else float("nan")
    result["pkg_power_w"] = float(power.group(1)) / 1000 if power else float("nan")
    frequencies = []
    in_frequency_table = False
    for line in text.splitlines():
        if line.strip().startswith("CPU P-State Average Frequency (excluding CPU idle time)"):
            in_frequency_table = True
            continue
        if in_frequency_table and "CPU/Package" in line and "," in line:
            try:
                frequencies.append(float(line.split(",")[1].strip()))
            except ValueError:
                pass
        elif in_frequency_table and frequencies and not line.strip():
            break
    result["active_freq_mhz"] = mean(frequencies) if frequencies else float("nan")
    return result


def read_emon(path: Path) -> dict:
    values = {"instructions_per_ref_cycle": [], "cache_miss_per_kinst": []}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            for name in values:
                try:
                    values[name].append(float(row[name]))
                except (KeyError, TypeError, ValueError):
                    pass
    return {name: mean(items) if items else float("nan") for name, items in values.items()}


def read_emon_timeseries(path: Path) -> dict:
    columns = ("freq_ghz", "instructions_per_ref_cycle", "cache_miss_per_kinst")
    samples = defaultdict(lambda: {column: [] for column in columns})
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            sample = int(row["sample"])
            for column in columns:
                try:
                    samples[sample][column].append(float(row[column]))
                except (KeyError, TypeError, ValueError):
                    pass
    return {
        column: [(sample, mean(values[column])) for sample, values in sorted(samples.items()) if values[column]]
        for column in columns
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--linux-repo",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "passmark-socwatch-emon-linux",
        help="Path to the sibling Linux repository",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "cross_os_pilot_comparison.png",
        help="Output PNG path",
    )
    args = parser.parse_args()

    windows_repo = Path(__file__).resolve().parents[1]
    windows_run = windows_repo / "reports/telemetry_correlation_report" / SKU / WINDOWS_RUN
    windows_scores = read_windows_scores(windows_run / "PassMark_PerfRes.txt")
    windows_soc = read_socwatch(windows_run / "socwatch.csv")
    windows_emon = read_emon(windows_run / "analysis/emon_timeseries_tidy.csv")
    windows_series = read_emon_timeseries(windows_run / "analysis/emon_timeseries_tidy.csv")
    ubuntu_runs = []
    for label, run_id, color in UBUNTU_RUNS:
        run = args.linux_repo / "reports/telemetry_correlation_report" / SKU / run_id
        ubuntu_runs.append({
            "label": label,
            "run_id": run_id,
            "color": color,
            "scores": read_ubuntu_scores(run / "results_console_all.yml"),
            "soc": read_socwatch(run / "socwatch/socwatch.csv"),
            "emon": read_emon(run / "analysis/emon_timeseries_tidy.csv"),
            "series": read_emon_timeseries(run / "analysis/emon_timeseries_tidy.csv"),
        })

    panels = [
        ("CPU Mark", [windows_scores["CPU Mark (Composite average)"]] + [run["scores"]["SUMM_CPU"] for run in ubuntu_runs], "score"),
        ("Memory Mark", [windows_scores["Memory Mark (Composite average)"]] + [run["scores"]["SUMM_ME"] for run in ubuntu_runs], "score"),
        ("Average package power", [windows_soc["pkg_power_w"]] + [run["soc"]["pkg_power_w"] for run in ubuntu_runs], "W"),
        ("Average active frequency", [windows_soc["active_freq_mhz"]] + [run["soc"]["active_freq_mhz"] for run in ubuntu_runs], "MHz"),
        ("Instructions per unhalted reference cycle", [windows_emon["instructions_per_ref_cycle"]] + [run["emon"]["instructions_per_ref_cycle"] for run in ubuntu_runs], "ratio; not conventional IPC"),
        ("LLC misses per 1,000 retired instructions", [windows_emon["cache_miss_per_kinst"]] + [run["emon"]["cache_miss_per_kinst"] for run in ubuntu_runs], "misses / 1k instructions"),
    ]

    fig, axes = plt.subplots(3, 2, figsize=(13, 10))
    fig.suptitle("Windows / Ubuntu PassMark Pilot", fontsize=17, fontweight="bold")
    fig.text(
        0.5,
        0.935,
        f"One capture each | Windows: Run All, {windows_soc['duration_sec']:.0f} s | "
        + " | ".join(f"Ubuntu {run['label']}: {run['soc']['duration_sec']:.0f} s" for run in ubuntu_runs)
        + " | suite coverage differs",
        ha="center",
        fontsize=10,
    )
    colors = [WINDOWS_COLOR] + [run["color"] for run in ubuntu_runs]
    labels = ["Windows UltimatePerformance"] + [f"Ubuntu {run['label']}" for run in ubuntu_runs]

    for axis, (title, values, units) in zip(axes.flat, panels):
        bars = axis.barh(labels, values, color=colors, height=0.56)
        axis.set_title(title, loc="left", fontsize=12, fontweight="bold")
        axis.set_xlabel(units, fontsize=9)
        axis.grid(axis="x", color="#d9dfe2", linewidth=0.8)
        axis.set_axisbelow(True)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0, labelsize=9)
        axis.tick_params(axis="x", labelsize=8, colors="#4b5960")
        axis.set_xlim(0, max(values) * 1.33 if max(values) > 0 else 1)
        for bar, value in zip(bars, values):
            axis.text(
                value + max(values) * 0.025,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.3f}" if "reference cycle" in title or "LLC" in title else f"{value:,.1f}",
                va="center",
                fontsize=9,
                color="#26343a",
            )

    fig.text(
        0.5,
        0.02,
        "n=1 per OS. Whole-capture telemetry is not phase-aligned to sub-tests; "
        "the reference-cycle ratio is not IPC. Descriptive pilot, not an OS ranking.",
        ha="center",
        fontsize=9,
        color="#4b5960",
    )
    fig.tight_layout(rect=(0.03, 0.06, 0.98, 0.91), h_pad=2.0, w_pad=1.5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, bbox_inches="tight")
    plt.close(fig)

    time_output = args.output.with_name("cross_os_pilot_emon_timeseries.png")
    fig, axes = plt.subplots(3, 3, figsize=(18, 10), sharex="col")
    fig.suptitle("EMON sample trends across each full capture", fontsize=16, fontweight="bold")
    fig.text(
        0.5,
        0.94,
        "Different suite coverage and capture lengths; samples are not aligned to PassMark phases or process IDs",
        ha="center",
        fontsize=10,
    )
    run_columns = [("Windows UltimatePerformance", windows_series, WINDOWS_COLOR, len(windows_series["freq_ghz"]), windows_soc["pkg_power_w"])]
    run_columns.extend((f"Ubuntu {run['label']}", run["series"], run["color"], len(run["series"]["freq_ghz"]), run["soc"]["pkg_power_w"]) for run in ubuntu_runs)
    time_metrics = (
        ("freq_ghz", "Mean EMON frequency across logical CPUs (GHz; includes idle samples)"),
        ("instructions_per_ref_cycle", "Instructions per unhalted reference cycle (not IPC)"),
        ("cache_miss_per_kinst", "LLC misses per 1,000 retired instructions"),
    )
    for column, (run_label, series, color, sample_count, avg_power) in enumerate(run_columns):
        axes[0, column].set_title(f"{run_label}\n{sample_count} samples; SoC Watch avg package power {avg_power:.2f} W", fontsize=10)
        for row, (metric, ylabel) in enumerate(time_metrics):
            points = series[metric]
            axes[row, column].plot([sample for sample, _ in points], [value for _, value in points], color=color, linewidth=0.8, alpha=0.7)
            axes[row, column].set_ylabel(ylabel, fontsize=8)
            axes[row, column].grid(True, color="#d9dfe2", linewidth=0.7)
            axes[row, column].spines[["top", "right"]].set_visible(False)
            axes[row, column].tick_params(axis="both", labelsize=8)
            axes[row, column].set_xlabel("EMON sample index (~1 sample/sec)", fontsize=8)
    fig.tight_layout(rect=(0.03, 0.04, 0.98, 0.91), h_pad=1.6, w_pad=1.8)
    fig.savefig(time_output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {args.output} and {time_output}")


if __name__ == "__main__":
    main()