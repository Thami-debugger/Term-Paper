"""
scoring.py
----------
Implements the Boltzmann likelihood model and Bayesian goal posterior
from Ramírez & Geffner (AAAI-10).

Model
-----
For each candidate goal G_i with costs c(G_i, O) and c(G_i, ~O):

    P(O | G_i)  ∝ exp(-β · c(G_i, O))
    P(O | ~G_i) ∝ exp(-β · c(G_i, ~O))

Posterior (equal priors assumed by default):

    P(G_i | O) ∝ P(O | G_i) · P(G_i)

Normalised using the log-sum-exp trick for numerical stability.

Metrics
-------
  Q  : 1 if the true goal is among the highest-posterior goals, else 0
  S  : number of goals tied at the maximum posterior (specificity; lower = better)
"""

import math
from dataclasses import dataclass, field


INF_COST = 1_000_000  # must match solver.py


@dataclass
class HypothesisResult:
    """Stores costs and derived probabilities for one candidate goal."""
    index: int
    atoms: list[str]
    cost_O: float = INF_COST        # c(G, O)  — compliant cost
    cost_not_O: float = INF_COST    # c(G, ~O) — non-compliant cost
    delta: float = 0.0              # c(G, O) - c(G, ~O)
    log_likelihood: float = 0.0
    posterior: float = 0.0
    is_true_goal: bool = False


def compute_posteriors(
    costs: list[tuple[float, float]],   # [(c_O_0, c_notO_0), ...]
    hyps: list[list[str]],              # atom lists for each hypothesis
    true_goal_index: int,
    beta: float = 1.0,
    prior: list[float] | None = None,   # uniform if None
) -> list[HypothesisResult]:
    """
    Compute posterior probability for each candidate goal.

    Parameters
    ----------
    costs            : list of (c_O, c_not_O) pairs, one per hypothesis
    hyps             : list of goal atom lists
    true_goal_index  : index of the hidden true goal in hyps
    beta             : Boltzmann temperature parameter (default 1.0)
    prior            : goal priors (uniform if None)

    Returns
    -------
    List of HypothesisResult, sorted by descending posterior.
    """
    n = len(hyps)
    if prior is None:
        prior = [1.0 / n] * n

    results = []
    for i, (atoms, (c_O, c_not_O)) in enumerate(zip(hyps, costs)):
        r = HypothesisResult(
            index=i,
            atoms=atoms,
            cost_O=c_O,
            cost_not_O=c_not_O,
            delta=c_O - c_not_O,
            is_true_goal=(i == true_goal_index),
        )
        # Log-likelihood: -β · c(G, O)
        # When c_O == INF_COST (unsolvable), likelihood → 0 → log = -∞
        if c_O >= INF_COST:
            r.log_likelihood = -math.inf
        else:
            r.log_likelihood = -beta * c_O

        results.append(r)

    # Add log prior
    log_unnorm = [
        r.log_likelihood + math.log(p) if p > 0 else -math.inf
        for r, p in zip(results, prior)
    ]

    # Normalise with log-sum-exp for numerical stability
    finite = [v for v in log_unnorm if math.isfinite(v)]
    if not finite:
        # All hypotheses unsolvable: uniform posterior
        for r in results:
            r.posterior = 1.0 / n
    else:
        max_log = max(finite)
        log_Z = max_log + math.log(
            sum(math.exp(v - max_log) for v in log_unnorm if math.isfinite(v))
        )
        for r, lv in zip(results, log_unnorm):
            if math.isfinite(lv):
                r.posterior = math.exp(lv - log_Z)
            else:
                r.posterior = 0.0

    results.sort(key=lambda r: r.posterior, reverse=True)
    return results


# -----------------------------------------------------------------------
# Evaluation metrics Q and S
# -----------------------------------------------------------------------

def compute_Q_S(results: list[HypothesisResult]) -> tuple[float, int]:
    """
    Compute recognition quality (Q) and specificity (S).

    Q = 1.0 if the true goal shares the maximum posterior, else 0.0
    S = number of goals tied at the maximum posterior

    Returns (Q, S).
    """
    if not results:
        return 0.0, 0

    max_posterior = results[0].posterior  # list is sorted descending

    # Goals tied at the maximum (within floating-point tolerance)
    tol = 1e-9
    top_goals = [r for r in results if abs(r.posterior - max_posterior) < tol]

    S = len(top_goals)
    Q = 1.0 if any(r.is_true_goal for r in top_goals) else 0.0
    return Q, S


def summarise(results: list[HypothesisResult]) -> None:
    """Pretty-print the posterior distribution."""
    print(f"{'#':>3}  {'Posterior':>10}  {'ΔCost':>8}  {'True?':>6}  Goal atoms")
    print("-" * 80)
    for r in results:
        marker = "← TRUE" if r.is_true_goal else ""
        delta_str = f"{r.delta:+.1f}" if r.cost_O < INF_COST else "  ∞"
        print(
            f"{r.index:>3}  {r.posterior:>10.4f}  {delta_str:>8}  "
            f"{'yes' if r.is_true_goal else 'no':>6}  "
            f"{', '.join(r.atoms[:3])}{'...' if len(r.atoms) > 3 else ''}  {marker}"
        )
    Q, S = compute_Q_S(results)
    print(f"\nQ = {Q:.1f}   S = {S}")
