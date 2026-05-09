"""
run_experiments.py
------------------
Top-level script to reproduce Table 1 from Ramírez & Geffner (AAAI-10).

Runs the evaluation pipeline across all selected domains and observation
levels, then prints a combined summary table.

Usage:
    python run_experiments.py [--domains blocks-world easy-ipc-grid ...] \
                              [--obs-levels 10 30 50 70 100] \
                              [--beta 1.0] [--timeout 300] \
                              [--data-dir ../benchmarks/experiments] \
                              [--out-dir ../results]

Defaults:
    --domains    : blocks-world easy-ipc-grid
    --obs-levels : 10 30 50 70 100
    --beta       : 1.0
    --timeout    : 300 (seconds per planner call)
    --data-dir   : ../benchmarks/experiments  (relative to this script)
    --out-dir    : ../results
"""

import os
import sys
import argparse
import json
from pathlib import Path

# Ensure src/ is on path
sys.path.insert(0, os.path.dirname(__file__))

from evaluate import evaluate_domain, save_results

# Default domains to replicate (matching the paper's two benchmark domains)
DEFAULT_DOMAINS = ['blocks-world', 'easy-ipc-grid']
DEFAULT_OBS_LEVELS = [10, 30, 50, 70, 100]


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce Ramírez & Geffner AAAI-10 Table 1"
    )
    parser.add_argument(
        '--domains', nargs='+', default=DEFAULT_DOMAINS,
        help='Domain names to evaluate (subdirectories of data-dir)'
    )
    parser.add_argument(
        '--obs-levels', nargs='+', type=int, default=DEFAULT_OBS_LEVELS,
        help='Observation coverage levels (%%) to evaluate'
    )
    parser.add_argument('--beta', type=float, default=1.0,
                        help='Boltzmann β parameter (default: 1.0)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='Planner timeout in seconds (default: 300)')
    parser.add_argument(
        '--data-dir',
        default=os.path.join(os.path.dirname(__file__), '..', 'benchmarks', 'experiments'),
        help='Path to benchmark experiments directory'
    )
    parser.add_argument(
        '--out-dir',
        default=os.path.join(os.path.dirname(__file__), '..', 'results'),
        help='Directory to write result files'
    )
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Verify domains exist
    available = []
    for domain in args.domains:
        path = os.path.join(data_dir, domain)
        if os.path.isdir(path):
            available.append(domain)
        else:
            print(f"[WARN] Domain directory not found: {path}")
    if not available:
        print("No valid domain directories found. Check --data-dir.")
        sys.exit(1)

    all_results: dict[str, list[dict]] = {}

    print("=" * 60)
    print("  Probabilistic Plan Recognition — Reproduction Study")
    print(f"  β = {args.beta}  |  timeout = {args.timeout}s")
    print("=" * 60)

    for domain in available:
        domain_path = os.path.join(data_dir, domain)
        print(f"\n>>> Domain: {domain}")

        domain_results = []
        for level in sorted(args.obs_levels):
            level_path = os.path.join(domain_path, str(level))
            if not os.path.isdir(level_path):
                print(f"  [skip] obs level {level}% not found")
                continue

            level_results = evaluate_domain(
                domain_path,
                obs_level=level,
                beta=args.beta,
                timeout=args.timeout,
                verbose=args.verbose,
            )
            domain_results.extend(level_results)

        all_results[domain] = domain_results

        # Save per-domain results
        out_base = os.path.join(out_dir, f"{domain}_results")
        save_results(domain_results, out_base + '.csv')

    # ----------------------------------------------------------------
    # Combined summary table (mirrors Table 1 format)
    # ----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  SUMMARY TABLE  (Q = accuracy, S = specificity)")
    print("=" * 60)
    print(f"{'Domain':<22}  {'Obs%':>5}  {'N':>4}  {'Q':>6}  {'S':>6}")
    print("-" * 60)

    for domain in available:
        results = all_results.get(domain, [])
        if not results:
            continue
        levels = sorted(set(r['obs_level'] for r in results))
        for lv in levels:
            subset = [r for r in results if r['obs_level'] == lv]
            Qm = sum(r['Q'] for r in subset) / len(subset)
            Sm = sum(r['S'] for r in subset) / len(subset)
            print(f"{domain:<22}  {lv:>5}  {len(subset):>4}  {Qm:>6.3f}  {Sm:>6.3f}")
        print()

    # Save combined JSON
    combined_path = os.path.join(out_dir, 'all_results.json')
    with open(combined_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"Combined results saved to: {combined_path}")


if __name__ == '__main__':
    main()
