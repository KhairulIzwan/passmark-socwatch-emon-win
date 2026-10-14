"""
analyze_all.py
One-shot wrapper: for every completed run folder under the Results directory,
(1) runs analyze_run.py to produce the 4 single-run plots (timeseries overview,
    per-core freq heatmap, C-state residency, PassMark percentiles), skipping
    runs that already have an analysis/ folder (unless --force is passed), then
(2) runs cross_run_analysis.py once to refresh the combined CSV/report/plots.

Usage:
    python analyze_all.py ["C:\\...\\Results"] [--force]

    --force   re-run analyze_run.py even for runs that already have an analysis/
              folder (useful after changing analyze_run.py itself).
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def is_complete_run(run_dir: Path) -> bool:
    return (run_dir / "PassMark_PerfRes.txt").exists() and (run_dir / "socwatch.csv").exists()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv[1:]
    root = Path(args[0]) if args else Path(
        r"C:\Users\Local_Admin\Desktop\passmark-socwatch-emon-win\Results")

    run_dirs = [d for d in sorted(root.iterdir())
                if d.is_dir() and re.match(r"\d{8}_\d{6}", d.name)]

    print(f"Scanning {root} ...")
    for run_dir in run_dirs:
        if not is_complete_run(run_dir):
            print(f"  [skip]  {run_dir.name} (incomplete / still in progress)")
            continue
        if (run_dir / "analysis").exists() and not force:
            print(f"  [done]  {run_dir.name} (analysis/ already exists, use --force to redo)")
            continue
        print(f"  [run]   {run_dir.name}")
        result = subprocess.run(
            [sys.executable, str(HERE / "analyze_run.py"), str(run_dir)],
            capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    !! analyze_run.py failed for {run_dir.name}:\n{result.stderr}")
        else:
            print(f"    -> OK")

    print("\nRefreshing cross-run report ...")
    result = subprocess.run(
        [sys.executable, str(HERE / "cross_run_analysis.py"), str(root)],
        capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"!! cross_run_analysis.py failed:\n{result.stderr}")


if __name__ == "__main__":
    main()
