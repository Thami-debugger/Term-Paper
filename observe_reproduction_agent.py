#!/usr/bin/env python3
"""
Observable Reproduction Agent

A practical, inspectable runner for reproducing the plan-recognition paper
results using the existing src/ pipeline.

What this script adds over src/run_experiments.py:
- Per-archive live progress so runs are easy to observe
- Optional instance cap for quick smoke tests
- Optional comparison against known paper targets (when available)
- Consolidated outputs in results/
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

# Ensure src/ is importable when this file is run from repo root.
ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from evaluate import run_instance, save_results  # type: ignore


DEFAULT_DOMAINS = [
    "blocks-world",
    "easy-ipc-grid",
    "logistics",
    "intrusion-detection",
    "campus",
    "kitchen",
]
DEFAULT_OBS_LEVELS = [10, 30, 50, 70, 100]
DEFAULT_PLANNERS = ["HSP", "LAMA", "GREEDY_LAMA"]

PLANNER_DISPLAY = {
    "HSP": "HSP",
    "LAMA": "LAMA",
    "GREEDY_LAMA": "Greedy LAMA",
}

# A small built-in subset from comments in test_with_dataset.py.
# You can pass --paper-targets for your exact table values.
DEFAULT_PAPER_TARGETS = {
    "blocks-world": {
        50: {
            "HSP": {"T": 1423.05, "Q": 1.0, "S": 2.23},
            "LAMA": {"T": 241.77, "Q": 1.0, "S": 2.23},
            "Greedy LAMA": {"T": 53.0, "Q": 0.54, "S": 1.23},
        }
    },
    "easy-ipc-grid": {
        50: {
            "HSP": {"T": 202.69, "Q": 1.0, "S": 1.0},
            "LAMA": {"T": 71.77, "Q": 1.0, "S": 1.0},
            "Greedy LAMA": {"T": 9.2, "Q": 1.0, "S": 1.0},
        }
    },
}


@dataclass
class LevelSummary:
    planner: str
    domain: str
    obs_level: int
    n: int
    t_mean: float
    q_mean: float
    s_mean: float


def _load_targets(target_path: str | None) -> Dict[str, Dict[int, Dict[str, Dict[str, float]]]]:
    if not target_path:
        return DEFAULT_PAPER_TARGETS

    with open(target_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Normalize level keys to int.
    normalized: Dict[str, Dict[int, Dict[str, Dict[str, float]]]] = {}
    for domain, levels in raw.items():
        normalized[domain] = {}
        for level, planner_values in levels.items():
            normalized[domain][int(level)] = {}
            for planner_name, metrics in planner_values.items():
                normalized[domain][int(level)][planner_name] = {
                    "T": float(metrics["T"]),
                    "Q": float(metrics["Q"]),
                    "S": float(metrics["S"]),
                }
    return normalized


def _find_archives(level_dir: Path) -> List[Path]:
    return [Path(p) for p in sorted(glob.glob(str(level_dir / "*.tar.bz2")))]


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def run_observable_reproduction(
    planner_profile: str,
    data_dir: Path,
    domains: List[str],
    obs_levels: List[int],
    beta: float,
    timeout: int,
    out_dir: Path,
    max_instances: int | None,
    verbose: bool,
) -> tuple[Dict[str, List[dict]], List[LevelSummary]]:
    all_results: Dict[str, List[dict]] = {}
    level_summaries: List[LevelSummary] = []

    print("=" * 72)
    print(f"Observable Reproduction Agent [{PLANNER_DISPLAY.get(planner_profile, planner_profile)}]")
    print("=" * 72)
    print(f"Data dir : {data_dir}")
    print(f"Domains  : {', '.join(domains)}")
    print(f"Obs%     : {obs_levels}")
    print(f"beta     : {beta}")
    print(f"timeout  : {timeout}s")
    if max_instances is not None:
        print(f"max inst : {max_instances} per level")
    print("=" * 72)

    for domain in domains:
        domain_dir = data_dir / domain
        if not domain_dir.is_dir():
            print(f"[WARN] Missing domain directory: {domain_dir}")
            continue

        print(f"\n[DOMAIN] {domain}")
        domain_results: List[dict] = []

        for level in obs_levels:
            level_dir = domain_dir / str(level)
            if not level_dir.is_dir():
                print(f"  [SKIP] {level}% not found")
                continue

            archives = _find_archives(level_dir)
            if not archives:
                print(f"  [SKIP] {level}% has no archives")
                continue

            if max_instances is not None:
                archives = archives[:max_instances]

            print(f"  [LEVEL {level}%] Running {len(archives)} archives")
            level_results: List[dict] = []

            for idx, archive in enumerate(archives, start=1):
                print(f"    [{idx}/{len(archives)}] {archive.name}")
                start = time.perf_counter()
                result = run_instance(
                    str(archive),
                    beta=beta,
                    timeout=timeout,
                    planner_profile=planner_profile,
                    verbose=verbose,
                )
                elapsed = time.perf_counter() - start
                if result is None:
                    print("      -> skipped (compile/solve issue)")
                    continue

                result["obs_level"] = level
                result["domain"] = domain
                result["runtime_sec"] = elapsed
                level_results.append(result)
                print(
                    f"      -> T={elapsed:.2f}s Q={result['Q']:.3f} S={result['S']:.3f}"
                )

            if level_results:
                t_mean = _mean([r["runtime_sec"] for r in level_results])
                q_mean = _mean([r["Q"] for r in level_results])
                s_mean = _mean([r["S"] for r in level_results])
                summary = LevelSummary(
                    planner=planner_profile,
                    domain=domain,
                    obs_level=level,
                    n=len(level_results),
                    t_mean=t_mean,
                    q_mean=q_mean,
                    s_mean=s_mean,
                )
                level_summaries.append(summary)
                domain_results.extend(level_results)
                print(
                    f"  [LEVEL {level}% DONE] n={summary.n} "
                    f"T={summary.t_mean:.2f}s Q={summary.q_mean:.3f} S={summary.s_mean:.3f}"
                )
            else:
                print(f"  [LEVEL {level}% DONE] no valid instances")

        all_results[domain] = domain_results

        # Persist per-domain results.
        if domain_results:
            out_base = out_dir / f"{domain}_{planner_profile.lower()}_observable_results"
            save_results(domain_results, str(out_base) + ".csv")

    return all_results, level_summaries


def print_summary_table(level_summaries: List[LevelSummary]) -> None:
    print("\n" + "=" * 72)
    print("Summary Table (Your Run)")
    print("=" * 72)
    print(f"{'Planner':<14} {'Domain':<22} {'O':>5} {'N':>5} {'T(s)':>10} {'Q':>8} {'S':>8}")
    print("-" * 72)

    if not level_summaries:
        print("No completed results.")
        return

    for item in sorted(level_summaries, key=lambda x: (x.planner, x.domain, x.obs_level)):
        print(
            f"{PLANNER_DISPLAY.get(item.planner, item.planner):<14} "
            f"{item.domain:<22} {item.obs_level:>5} {item.n:>5} {item.t_mean:>10.2f} "
            f"{item.q_mean:>8.3f} {item.s_mean:>8.3f}"
        )


def print_paper_comparison(
    level_summaries: List[LevelSummary],
    targets: Dict[str, Dict[int, Dict[str, Dict[str, float]]]],
) -> None:
    print("\n" + "=" * 72)
    print("Paper Comparison")
    print("=" * 72)
    print(
        f"{'Planner':<14} {'Domain':<18} {'O':>4} "
        f"{'T_run':>10} {'Q_run':>8} {'S_run':>8} "
        f"{'T_ref':>10} {'Q_ref':>8} {'S_ref':>8} "
        f"{'dQ':>8} {'dS':>8}"
    )
    print("-" * 72)

    rows = 0
    lookup = {(s.planner, s.domain, s.obs_level): s for s in level_summaries}

    for planner in DEFAULT_PLANNERS:
        planner_ref_key = PLANNER_DISPLAY.get(planner, planner)
        for domain, levels in sorted(targets.items()):
            for level, planners in sorted(levels.items()):
                summary = lookup.get((planner, domain, level))
                if summary is None:
                    continue
                ref = planners.get(planner_ref_key)
                if ref is None:
                    continue
                dq = summary.q_mean - ref["Q"]
                ds = summary.s_mean - ref["S"]
                print(
                    f"{planner_ref_key:<14} {domain:<18} {level:>4} "
                    f"{summary.t_mean:>10.2f} {summary.q_mean:>8.3f} {summary.s_mean:>8.3f} "
                    f"{ref['T']:>10.2f} {ref['Q']:>8.3f} {ref['S']:>8.3f} "
                    f"{dq:>8.3f} {ds:>8.3f}"
                )
                rows += 1

    if rows == 0:
        print("No overlap between run outputs and reference targets.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an observable plan-recognition reproduction study."
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "benchmarks" / "experiments"),
        help="Path to benchmark experiments root.",
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        default=DEFAULT_DOMAINS,
        help="Domain names under data-dir.",
    )
    parser.add_argument(
        "--obs-levels",
        nargs="+",
        type=int,
        default=DEFAULT_OBS_LEVELS,
        help="Observation levels to run.",
    )
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--planners",
        nargs="+",
        default=DEFAULT_PLANNERS,
        help="Planner profiles to run: HSP LAMA GREEDY_LAMA",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "results"),
        help="Directory for outputs.",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        default=None,
        help="Optional cap per domain-level for quick testing.",
    )
    parser.add_argument(
        "--compare-paper",
        action="store_true",
        help="Print differences vs reference paper metrics.",
    )
    parser.add_argument(
        "--paper-targets",
        default=None,
        help="Optional JSON file with target Q/S values.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: Dict[str, Dict[str, List[dict]]] = {}
    level_summaries: List[LevelSummary] = []

    for planner in args.planners:
        planner_key = planner.upper()
        if planner_key not in PLANNER_DISPLAY:
            raise ValueError(
                f"Unsupported planner '{planner}'. "
                "Use one or more of: HSP LAMA GREEDY_LAMA"
            )

        planner_results, planner_summaries = run_observable_reproduction(
            planner_profile=planner_key,
            data_dir=data_dir,
            domains=args.domains,
            obs_levels=sorted(args.obs_levels),
            beta=args.beta,
            timeout=args.timeout,
            out_dir=out_dir,
            max_instances=args.max_instances,
            verbose=args.verbose,
        )
        all_results[planner_key] = planner_results
        level_summaries.extend(planner_summaries)

    print_summary_table(level_summaries)

    combined_json = out_dir / "observable_all_results.json"
    with open(combined_json, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved combined JSON: {combined_json}")

    if args.compare_paper:
        targets = _load_targets(args.paper_targets)
        print_paper_comparison(level_summaries, targets)


if __name__ == "__main__":
    main()
