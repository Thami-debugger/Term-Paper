"""
assignment_demo.py
==================
Step-by-step demonstration of all four assignment components from
Ramirez & Geffner (AAAI-10) "Probabilistic Plan Recognition Using Off-the-Shelf Classical Planners".

Components demonstrated
-----------------------
1. PDDL Compiler      - src/compiler.py  (Definition 2 & Proposition 3)
2. Planner Integration - src/solver.py   (Fast Downward wrapper)
3. Bayesian Scoring   - src/scoring.py   (Equations 2-5)
4. Evaluation Pipeline - src/evaluate.py (prefix sampling -> Q/S metrics)

Usage
-----
    python assignment_demo.py [--domain blocks-world] [--obs-level 10]
                              [--max-instances 3] [--beta 1.0]
                              [--timeout 120] [--planner HSP]
                              [--data-dir benchmarks/experiments]

Run with --help for full options.
"""

import argparse
import glob
import json
import math
import os
import sys
import tarfile
import tempfile
import time
import textwrap

# -- Make src/ importable ------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from compiler import compile_problems, parse_obs, parse_hyps, parse_real_hyp
from solver import solve_pair, PLANNER_PROFILES
from scoring import compute_posteriors, compute_Q_S


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

DIVIDER = "=" * 72
SUBDIV  = "-" * 72

def banner(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)

def section(title: str) -> None:
    print(f"\n{SUBDIV}")
    print(f"  {title}")
    print(SUBDIV)

def indent(text: str, spaces: int = 4) -> str:
    return textwrap.indent(text, " " * spaces)

def head(text: str, n: int = 30) -> str:
    """Return first n non-blank lines of text."""
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[:n]) + ("\n  [... truncated ...]" if len(lines) > n else "")


# -----------------------------------------------------------------------------
# Component 1 - PDDL Compiler
# -----------------------------------------------------------------------------

def demo_component1(archive_path: str, tmpdir: str) -> dict:
    """
    Component 1: PDDL Compiler
    ---------------------------
    Implements Definition 2 and Proposition 3 of the paper.

    Input : domain.pddl, template.pddl, hyps.dat, obs.dat
    Output: domain_obs.pddl (augmented), compliant_<i>.pddl, noncompliant_<i>.pddl
    """
    banner("COMPONENT 1 -- PDDL Compiler  (Definition 2 & Proposition 3)")

    # -- Extract archive ---------------------------------------------------
    with tarfile.open(archive_path, 'r:bz2') as t:
        t.extractall(tmpdir)

    domain_path   = os.path.join(tmpdir, 'domain.pddl')
    template_path = os.path.join(tmpdir, 'template.pddl')
    hyps_path     = os.path.join(tmpdir, 'hyps.dat')
    obs_path      = os.path.join(tmpdir, 'obs.dat')
    real_hyp_path = os.path.join(tmpdir, 'real_hyp.dat')

    # -- Show raw inputs ---------------------------------------------------
    section("1a. Candidate Goals  (hyps.dat)")
    hyps = parse_hyps(hyps_path)
    print(f"  Number of candidate goals: {len(hyps)}")
    for i, atoms in enumerate(hyps):
        print(f"  G{i}: {', '.join(atoms)}")

    section("1b. Observation Sequence  (obs.dat)")
    obs_list = parse_obs(obs_path)
    print(f"  Observed actions ({len(obs_list)} steps):")
    for k, o in enumerate(obs_list):
        print(f"    o_{k}: {o}")

    real_hyp = parse_real_hyp(real_hyp_path)
    real_hyp_set = set(real_hyp)
    true_idx = next(
        (i for i, atoms in enumerate(hyps) if set(atoms) == real_hyp_set),
        0
    )
    print(f"\n  Hidden true goal: G{true_idx} = {', '.join(real_hyp)}")

    # -- Compile -----------------------------------------------------------
    section("1c. Compiling PDDL Problems")
    compile_out = os.path.join(tmpdir, 'compiled')
    print("  Running compile_problems() ...")
    compiled = compile_problems(domain_path, template_path, hyps_path, obs_path, compile_out)

    print("\n  Output files generated:")
    print(f"    * domain_obs.pddl          -- augmented domain with obs-tracking fluents")
    for i in range(len(hyps)):
        print(f"    * compliant_{i}.pddl        -- G{i} + p_last_obs  (must execute O)")
        print(f"    * noncompliant_{i}.pddl     -- G{i} + ~p_last_obs (must skip O)")

    # -- Show snippet of augmented domain ----------------------------------
    section("1d. Augmented Domain Snippet  (domain_obs.pddl)")
    with open(compiled['domain_obs']) as f:
        domain_obs_text = f.read()
    print(indent(head(domain_obs_text, 25)))

    # -- Show compliant vs non-compliant goals -----------------------------
    section("1e. Compiled Problem Goals  (G0 as example)")
    for label, path in [
        (f"compliant_0.pddl   (G0 + p_last_obs)", compiled['compliant'][0]),
        (f"noncompliant_0.pddl (G0 + ~p_last_obs)", compiled['noncompliant'][0]),
    ]:
        print(f"\n  [{label}]")
        with open(path) as f:
            text = f.read()
        # Extract the (:goal ...) block
        import re
        goal_match = re.search(r'(\(:goal.*?\))\s*\)', text, re.DOTALL)
        if goal_match:
            print(indent(goal_match.group(0)))
        else:
            print(indent(head(text, 10)))

    return {
        'compiled': compiled,
        'hyps': hyps,
        'obs_list': obs_list,
        'true_idx': true_idx,
        'domain_path': domain_path,
    }


# -----------------------------------------------------------------------------
# Component 2 - Planner Integration
# -----------------------------------------------------------------------------

def demo_component2(compiled: dict, hyps: list, planner_profile: str, timeout: int) -> list:
    """
    Component 2: Planner Integration
    ---------------------------------
    Calls Fast Downward on each compiled problem pair.

    For each hypothesis G_i:
        c(G_i, O)  = cost of cheapest plan that COMPLIES with observations
        c(G_i, ~O) = cost of cheapest plan that AVOIDS observations
    """
    banner("COMPONENT 2 -- Planner Integration  (Fast Downward)")

    section("2a. Planner Profile")
    print(f"  Selected profile : {planner_profile}")
    print(f"  Search flags     : {PLANNER_PROFILES.get(planner_profile.upper(), ['<unknown>'])}")
    print(f"  Timeout          : {timeout}s per problem")

    section("2b. Solving Problem Pairs")
    print(f"  Running Fast Downward for {len(hyps)} hypothesis/hypotheses ...\n")

    costs = []
    for i in range(len(hyps)):
        print(f"  Hypothesis G{i}: {', '.join(hyps[i])}")
        t0 = time.time()
        c_O, c_not_O = solve_pair(
            compiled['domain_obs'],
            compiled['compliant'][i],
            compiled['noncompliant'][i],
            timeout=timeout,
            planner_profile=planner_profile,
        )
        elapsed = time.time() - t0
        costs.append((c_O, c_not_O))

        c_O_str   = str(int(c_O))   if c_O   < 1_000_000 else "inf (unsolvable)"
        c_nO_str  = str(int(c_not_O)) if c_not_O < 1_000_000 else "inf (unsolvable)"
        delta     = c_O - c_not_O
        delta_str = f"{delta:+.0f}" if abs(delta) < 1_000_000 else "N/A"

        print(f"    c(G{i}, O)  = {c_O_str}")
        print(f"    c(G{i},~O)  = {c_nO_str}")
        print(f"    delta(G{i}, O)  = {delta_str}   [{elapsed:.1f}s]")
        print()

    return costs


# -----------------------------------------------------------------------------
# Component 3 - Bayesian Scoring
# -----------------------------------------------------------------------------

def demo_component3(costs: list, hyps: list, true_idx: int, beta: float) -> list:
    """
    Component 3: Bayesian Scoring Layer
    -------------------------------------
    Implements Equations 2-5 of the paper.

    P(O | G_i)  prop exp(-beta * c(G_i, O))
    P(G_i | O) prop P(O | G_i) * P(G_i)        [Bayes' rule, uniform prior]
    """
    banner("COMPONENT 3 -- Bayesian Scoring  (Equations 2-5)")

    section("3a. Boltzmann Likelihood Model")
    print(f"  beta (Boltzmann temperature) = {beta}")
    print(f"  P(O | G_i) prop exp(-beta * c(G_i, O))")
    print()

    INF = 1_000_000
    print(f"  {'G_i':<8} {'c(G,O)':>10} {'c(G,~O)':>10} {'delta(G,O)':>10} {'P(O|G) raw':>14}")
    print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*14}")
    for i, (c_O, c_nO) in enumerate(costs):
        delta = c_O - c_nO
        raw_lik = math.exp(-beta * c_O) if c_O < INF else 0.0
        c_O_s  = str(int(c_O))   if c_O  < INF else "inf"
        c_nO_s = str(int(c_nO))  if c_nO < INF else "inf"
        d_s    = f"{delta:+.0f}" if abs(delta) < INF else "N/A"
        print(f"  {'G'+str(i):<8} {c_O_s:>10} {c_nO_s:>10} {d_s:>10} {raw_lik:>14.6f}")

    section("3b. Posterior Probabilities  (Bayes' rule, uniform prior)")
    results = compute_posteriors(costs, hyps, true_idx, beta=beta)
    Q, S = compute_Q_S(results)

    print(f"  {'Rank':<6} {'G_i':<6} {'Posterior':>10} {'True?':>8} {'Goal atoms'}")
    print(f"  {'-'*6} {'-'*6} {'-'*10} {'-'*8} {'-'*30}")
    for rank, r in enumerate(results, 1):
        true_marker = "*  TRUE" if r.is_true_goal else ""
        atoms_str = ', '.join(r.atoms[:3]) + ('...' if len(r.atoms) > 3 else '')
        print(f"  {rank:<6} {'G'+str(r.index):<6} {r.posterior:>10.4f} {true_marker:>8}  {atoms_str}")

    section("3c. Recognition Metrics")
    print(f"  Q (accuracy)    = {Q:.2f}   (1.0 = true goal has highest posterior)")
    print(f"  S (specificity) = {S}      (number of goals tied at max posterior; lower = better)")

    return results


# -----------------------------------------------------------------------------
# Component 4 - Evaluation Pipeline
# -----------------------------------------------------------------------------

def demo_component4(domain_dir: str, obs_level: int, beta: float, timeout: int,
                    planner_profile: str, max_instances: int) -> None:
    """
    Component 4: Evaluation Pipeline
    ----------------------------------
    Iterates over all benchmark archives for one domain/obs-level.
    Observation sequences are pre-sampled as prefixes of optimal plans.

    Aggregates Q and S across all instances to reproduce Table 1 of the paper.
    """
    banner("COMPONENT 4 -- Evaluation Pipeline  (Table 1 reproduction)")

    level_dir = os.path.join(domain_dir, str(obs_level))
    archives = sorted(glob.glob(os.path.join(level_dir, '*.tar.bz2')))

    if not archives:
        print(f"  [SKIP] No archives found in: {level_dir}")
        return

    archives = archives[:max_instances]
    print(f"  Domain directory : {domain_dir}")
    print(f"  Observation level: {obs_level}%  (prefix of optimal plan)")
    print(f"  Archives to run  : {len(archives)}")
    print(f"  Planner profile  : {planner_profile}")
    print(f"  beta                : {beta}")
    print()

    section("4a. Prefix-Sampling Explanation")
    print(textwrap.dedent("""\
      For each benchmark instance the repository already provides obs.dat,
      which contains the observation sequence sampled as a k% prefix of an
      optimal plan for the hidden true goal.

      At k=10%  -> very few observations -> harder recognition
      At k=100% -> full plan visible    -> easier recognition

      The pipeline below processes each archive independently and then
      averages Q and S across all instances.
    """))

    section("4b. Running All Instances")
    all_Q, all_S = [], []
    failed = 0

    from evaluate import run_instance

    for idx, arch in enumerate(archives, 1):
        name = os.path.basename(arch)
        print(f"  [{idx}/{len(archives)}] {name}")
        t0 = time.time()
        result = run_instance(
            arch,
            beta=beta,
            timeout=timeout,
            planner_profile=planner_profile,
            verbose=False,
        )
        elapsed = time.time() - t0

        if result is None:
            print(f"    FAIL FAILED  ({elapsed:.1f}s)")
            failed += 1
            continue

        Q, S = result['Q'], result['S']
        all_Q.append(Q)
        all_S.append(S)
        status = "OK  Q=1" if Q == 1.0 else "FAIL  Q=0"
        print(f"    {status}  S={S}  ({elapsed:.1f}s)")

    section("4c. Aggregate Results  (Table 1 style)")
    n_total = len(archives)
    n_ok    = len(all_Q)

    if n_ok == 0:
        print("  No instances completed successfully.")
        return

    mean_Q = sum(all_Q) / n_ok
    mean_S = sum(all_S) / n_ok

    # Standard deviation
    if n_ok > 1:
        var_Q = sum((q - mean_Q) ** 2 for q in all_Q) / (n_ok - 1)
        var_S = sum((s - mean_S) ** 2 for s in all_S) / (n_ok - 1)
        std_Q = math.sqrt(var_Q)
        std_S = math.sqrt(var_S)
    else:
        std_Q = std_S = 0.0

    print()
    print(f"  Instances run      : {n_total}")
    print(f"  Instances OK       : {n_ok}  ({failed} failed)")
    print(f"  Observation level  : {obs_level}%")
    print()
    print(f"  {'Metric':<12} {'Mean':>8} {'Std Dev':>10}")
    print(f"  {'-'*12} {'-'*8} {'-'*10}")
    print(f"  {'Q (accuracy)':<12} {mean_Q:>8.3f} {std_Q:>10.3f}")
    print(f"  {'S (specific.)':<12} {mean_S:>8.3f} {std_S:>10.3f}")
    print()

    paper_ref = _paper_reference(os.path.basename(domain_dir), obs_level)
    if paper_ref:
        print(f"  Paper reference (HSP): Q={paper_ref.get('Q','?')}  S={paper_ref.get('S','?')}")

    return {'mean_Q': mean_Q, 'std_Q': std_Q, 'mean_S': mean_S, 'std_S': std_S,
            'n_ok': n_ok, 'n_total': n_total}


def _paper_reference(domain: str, obs_level: int) -> dict | None:
    """Load reference values from paper_targets.json if present."""
    targets_path = os.path.join(os.path.dirname(__file__), 'paper_targets.json')
    if not os.path.isfile(targets_path):
        return None
    with open(targets_path) as f:
        targets = json.load(f)
    key = f"{domain}_{obs_level}"
    return targets.get('HSP', {}).get(key)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description='COMS7044A -- Step-by-step demonstration of all 4 assignment components',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples
            --------
              # Quick demo on 1 blocks-world archive at 10% observations, HSP planner
              python assignment_demo.py

              # Test with LAMA planner on 3 instances at 50% observations
              python assignment_demo.py --planner LAMA --obs-level 50 --max-instances 3

              # Full blocks-world run at all obs levels
              python assignment_demo.py --obs-level 10 30 50 70 100 --max-instances 5
        """),
    )
    p.add_argument('--domain',         default='blocks-world',
                   help='Benchmark domain name (default: blocks-world)')
    p.add_argument('--obs-level',      type=int, nargs='+', default=[10],
                   help='Observation level(s) in percent (default: 10)')
    p.add_argument('--max-instances',  type=int, default=1,
                   help='Max archives to process per obs-level (default: 1)')
    p.add_argument('--beta',           type=float, default=1.0,
                   help='Boltzmann beta parameter (default: 1.0)')
    p.add_argument('--timeout',        type=int, default=120,
                   help='Per-problem planner timeout in seconds (default: 120)')
    p.add_argument('--planner',        default='HSP',
                   choices=['HSP', 'LAMA', 'GREEDY_LAMA'],
                   help='Planner profile (default: HSP)')
    p.add_argument('--data-dir',       default='benchmarks/experiments',
                   help='Root directory of benchmark archives')
    p.add_argument('--skip-pipeline',  action='store_true',
                   help='Only run Components 1-3 (skip the full evaluation pipeline)')
    return p.parse_args()


def main():
    args = parse_args()

    # Resolve domain directory
    base_dir = os.path.join(os.path.dirname(__file__), args.data_dir)
    domain_dir = os.path.join(base_dir, args.domain)

    if not os.path.isdir(domain_dir):
        print(f"ERROR: Domain directory not found: {domain_dir}")
        print(f"Available domains: {', '.join(sorted(os.listdir(base_dir)))}")
        sys.exit(1)

    # Pick one archive for Components 1-3
    first_obs = args.obs_level[0]
    level_dir = os.path.join(domain_dir, str(first_obs))
    archives  = sorted(glob.glob(os.path.join(level_dir, '*.tar.bz2')))

    if not archives:
        print(f"ERROR: No archives in {level_dir}")
        sys.exit(1)

    demo_archive = archives[0]

    print(DIVIDER)
    print("  COMS7044A -- PDDL Plan Recognition: Component-by-Component Demo")
    print("  Paper: Ramirez & Geffner, AAAI-10")
    print(DIVIDER)
    print(f"\n  Demo archive : {os.path.basename(demo_archive)}")
    print(f"  Domain       : {args.domain}")
    print(f"  Obs level    : {first_obs}%")
    print(f"  Planner      : {args.planner}")
    print(f"  beta            : {args.beta}")

    with tempfile.TemporaryDirectory() as tmpdir:
        # -- Component 1: PDDL Compiler ------------------------------------
        ctx = demo_component1(demo_archive, tmpdir)

        # -- Component 2: Planner ------------------------------------------
        costs = demo_component2(
            ctx['compiled'], ctx['hyps'],
            planner_profile=args.planner, timeout=args.timeout
        )

        # -- Component 3: Bayesian Scoring ---------------------------------
        demo_component3(costs, ctx['hyps'], ctx['true_idx'], beta=args.beta)

    # -- Component 4: Full Evaluation Pipeline -----------------------------
    if not args.skip_pipeline:
        for obs_level in args.obs_level:
            demo_component4(
                domain_dir,
                obs_level=obs_level,
                beta=args.beta,
                timeout=args.timeout,
                planner_profile=args.planner,
                max_instances=args.max_instances,
            )

    banner("DEMO COMPLETE")
    print(textwrap.dedent(f"""\
      All four assignment components have been demonstrated:

        Component 1 -- PDDL Compiler
          src/compiler.py :: compile_problems()
          Implements Definition 2 & Proposition 3 -- adds obs_reached_k fluents
          to the domain and generates compliant (G+O) and non-compliant (G+~O)
          problems for each candidate goal.

        Component 2 -- Planner Integration
          src/solver.py :: solve_pair()
          Wraps Fast Downward with three profiles: HSP (A*+LM-cut), LAMA,
          and Greedy LAMA. Returns c(G,O) and c(G,~O) for each hypothesis.

        Component 3 -- Bayesian Scoring
          src/scoring.py :: compute_posteriors()
          Boltzmann likelihood P(O|G) prop exp(-beta*c(G,O)), then Bayes' rule
          gives posterior P(G|O). Q=1 if true goal ranks first; S = #tied goals.

        Component 4 -- Evaluation Pipeline
          src/evaluate.py :: run_instance() / evaluate_domain()
          Processes all benchmark archives. Observations are k%-prefixes of
          optimal plans. Aggregates Q and S with mean +- std over all instances.
    """))


if __name__ == '__main__':
    main()
