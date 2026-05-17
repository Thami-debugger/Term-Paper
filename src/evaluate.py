"""
evaluate.py
-----------
Evaluation pipeline for reproducing Table 1 of Ramírez & Geffner (AAAI-10).

For each benchmark archive (.tar.bz2) in a domain/obs-level directory:
  1. Extract the archive to a temp folder.
  2. Call compiler.py to generate augmented domain + compliant/non-compliant problems.
  3. Call solver.py to get plan costs for each hypothesis.
  4. Call scoring.py to compute posteriors and Q / S metrics.
  5. Aggregate across all instances in the directory.

Usage (from within src/):
    python evaluate.py <domain_dir> [--beta 1.0] [--timeout 300] [--obs-level 10]

Example:
    python evaluate.py ../benchmarks/experiments/blocks-world --obs-level 50
"""

import os
import sys
import glob
import tarfile
import tempfile
import argparse
import csv
import json
import traceback
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, os.path.dirname(__file__))

from compiler import compile_problems, parse_real_hyp, parse_hyps
from solver import solve_pair
from scoring import compute_posteriors, compute_Q_S


# -----------------------------------------------------------------------
# Per-instance runner
# -----------------------------------------------------------------------

def run_instance(
    archive_path: str,
    beta: float = 1.0,
    timeout: int = 300,
    planner_profile: str = 'HSP',
    verbose: bool = False,
) -> dict | None:
    """
    Process one .tar.bz2 benchmark archive.

    Returns a dict with keys: archive, obs_level, Q, S, n_hyps,
    true_goal_index, costs_O, costs_notO, posteriors.
    Returns None if the instance could not be processed.
    """
    archive_path = os.path.abspath(archive_path)
    archive_name = os.path.basename(archive_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Extract archive ---
        try:
            with tarfile.open(archive_path, 'r:bz2') as t:
                t.extractall(tmpdir)
        except Exception as exc:
            print(f"[WARN] Could not extract {archive_name}: {exc}")
            return None

        domain_path = os.path.join(tmpdir, 'domain.pddl')
        template_path = os.path.join(tmpdir, 'template.pddl')
        hyps_path = os.path.join(tmpdir, 'hyps.dat')
        obs_path = os.path.join(tmpdir, 'obs.dat')
        real_hyp_path = os.path.join(tmpdir, 'real_hyp.dat')

        for p in (domain_path, template_path, hyps_path, obs_path, real_hyp_path):
            if not os.path.isfile(p):
                print(f"[WARN] Missing file {os.path.basename(p)} in {archive_name}")
                return None

        # --- Identify true goal index ---
        hyps = parse_hyps(hyps_path)
        real_hyp = parse_real_hyp(real_hyp_path)
        real_hyp_set = set(real_hyp)

        true_idx = None
        for i, atoms in enumerate(hyps):
            if set(atoms) == real_hyp_set:
                true_idx = i
                break

        if true_idx is None:
            # True goal not found among hypotheses — skip
            if verbose:
                print(f"[WARN] True goal not in hyps for {archive_name}")
            return None

        # --- Compile PDDL ---
        compile_out = os.path.join(tmpdir, 'compiled')
        try:
            compiled = compile_problems(
                domain_path, template_path, hyps_path, obs_path, compile_out
            )
        except Exception as exc:
            print(f"[WARN] Compilation failed for {archive_name}: {exc}")
            if verbose:
                traceback.print_exc()
            return None

        # --- Solve each hypothesis pair ---
        costs = []
        for i in range(len(hyps)):
            try:
                c_O, c_not_O = solve_pair(
                    compiled['domain_obs'],
                    compiled['compliant'][i],
                    compiled['noncompliant'][i],
                    timeout=timeout,
                    planner_profile=planner_profile,
                )
            except Exception as exc:
                print(f"[WARN] Solver failed for hyp {i} in {archive_name}: {exc}")
                return None
            costs.append((c_O, c_not_O))

        # --- Compute posteriors ---
        results = compute_posteriors(costs, hyps, true_idx, beta=beta)
        Q, S = compute_Q_S(results)

    if verbose:
        print(f"{archive_name}: Q={Q:.1f}  S={S}  true_idx={true_idx}")

    return {
        'archive': archive_name,
        'planner_profile': planner_profile,
        'Q': Q,
        'S': S,
        'n_hyps': len(hyps),
        'true_goal_index': true_idx,
        'costs_O': [c[0] for c in costs],
        'costs_not_O': [c[1] for c in costs],
        'posteriors': [r.posterior for r in sorted(results, key=lambda r: r.index)],
    }


# -----------------------------------------------------------------------
# Domain-level aggregation
# -----------------------------------------------------------------------

def evaluate_domain(
    domain_dir: str,
    obs_level: int | None = None,
    beta: float = 1.0,
    timeout: int = 300,
    planner_profile: str = 'HSP',
    verbose: bool = False,
) -> list[dict]:
    """
    Run all instances in a domain directory (or a specific obs-level sub-dir).

    domain_dir : e.g. benchmarks/experiments/blocks-world
    obs_level  : 10, 30, 50, 70, or 100 (None = all levels)
    """
    domain_dir = os.path.abspath(domain_dir)

    if obs_level is not None:
        search_dirs = [os.path.join(domain_dir, str(obs_level))]
    else:
        # All numeric sub-directories
        search_dirs = sorted(
            d for d in glob.glob(os.path.join(domain_dir, '*'))
            if os.path.isdir(d) and os.path.basename(d).isdigit()
        )

    all_results = []
    for sub_dir in search_dirs:
        level = int(os.path.basename(sub_dir))
        archives = sorted(glob.glob(os.path.join(sub_dir, '*.tar.bz2')))
        if not archives:
            continue

        level_results = []
        for arc in archives:
            res = run_instance(
                arc,
                beta=beta,
                timeout=timeout,
                planner_profile=planner_profile,
                verbose=verbose,
            )
            if res is not None:
                res['obs_level'] = level
                res['domain'] = os.path.basename(domain_dir)
                level_results.append(res)

        if level_results:
            Q_mean = sum(r['Q'] for r in level_results) / len(level_results)
            S_mean = sum(r['S'] for r in level_results) / len(level_results)
            n = len(level_results)
            print(
                f"  Obs {level:>3}%  |  n={n:>3}  |  "
                f"Q={Q_mean:.3f}  |  S={S_mean:.3f}"
            )
            all_results.extend(level_results)

    return all_results


# -----------------------------------------------------------------------
# Result export
# -----------------------------------------------------------------------

def save_results(results: list[dict], out_path: str) -> None:
    """Save results to a CSV and a JSON file."""
    base = os.path.splitext(out_path)[0]

    # CSV (summary columns only)
    csv_path = base + '.csv'
    fieldnames = ['domain', 'obs_level', 'archive', 'Q', 'S', 'n_hyps', 'true_goal_index']
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)

    # JSON (full detail)
    json_path = base + '.json'
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to:\n  {csv_path}\n  {json_path}")


# -----------------------------------------------------------------------
# CLI entry point
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate probabilistic plan recognition (Ramirez & Geffner AAAI-10)"
    )
    parser.add_argument('domain_dir', help='Path to domain benchmark directory')
    parser.add_argument('--beta', type=float, default=1.0,
                        help='Boltzmann temperature parameter (default: 1.0)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='Per-problem planner timeout in seconds (default: 300)')
    parser.add_argument(
        '--planner-profile',
        default='HSP',
        help='Planner profile: HSP, LAMA, GREEDY_LAMA',
    )
    parser.add_argument('--obs-level', type=int, default=None,
                        help='Observation coverage level: 10, 30, 50, 70, or 100 (default: all)')
    parser.add_argument('--out', default=None,
                        help='Output file base path (default: results/<domain>_results)')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    domain_name = os.path.basename(os.path.abspath(args.domain_dir))
    print(f"\n=== Evaluating domain: {domain_name} ===")
    if args.obs_level:
        print(f"    Observation level: {args.obs_level}%")
    print(
        f"    β = {args.beta}  |  timeout = {args.timeout}s  "
        f"|  planner = {args.planner_profile}\n"
    )

    results = evaluate_domain(
        args.domain_dir,
        obs_level=args.obs_level,
        beta=args.beta,
        timeout=args.timeout,
        planner_profile=args.planner_profile,
        verbose=args.verbose,
    )

    if not results:
        print("No results — check that archives exist and Fast Downward is installed.")
        sys.exit(1)

    # Summary table
    levels = sorted(set(r['obs_level'] for r in results))
    print(f"\n{'Obs%':>5}  {'N':>4}  {'Q (mean)':>10}  {'S (mean)':>10}")
    print("-" * 35)
    for lv in levels:
        subset = [r for r in results if r['obs_level'] == lv]
        Qm = sum(r['Q'] for r in subset) / len(subset)
        Sm = sum(r['S'] for r in subset) / len(subset)
        print(f"{lv:>5}  {len(subset):>4}  {Qm:>10.3f}  {Sm:>10.3f}")

    # Save
    out_base = args.out or os.path.join(
        os.path.dirname(__file__), '..', 'results', f"{domain_name}_results"
    )
    os.makedirs(os.path.dirname(os.path.abspath(out_base)), exist_ok=True)
    save_results(results, out_base + '.csv')


if __name__ == '__main__':
    main()
