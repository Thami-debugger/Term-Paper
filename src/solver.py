"""
solver.py
---------
Wraps Fast Downward to extract plan costs using selectable planner profiles.

Supported planner profiles:
    - HSP          : --search astar(lmcut())
    - LAMA         : --alias seq-sat-lama-2011
    - GREEDY_LAMA  : --alias lama-first
"""

import subprocess
import re
import os
import sys
import tempfile
import shutil
import time

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

INF_COST = 1_000_000  # sentinel for unsolvable

PLANNER_PROFILES: dict[str, list[str]] = {
    'HSP': ['--search', 'astar(lmcut())'],
    'LAMA': ['--alias', 'seq-sat-lama-2011'],
    'GREEDY_LAMA': ['--alias', 'lama-first'],
}

# Attempt to locate Fast Downward automatically
def _find_fast_downward() -> list[str]:
    """Return the command prefix to invoke Fast Downward."""
    # 1. Explicit environment variable
    fd_env = os.environ.get('FAST_DOWNWARD')
    if fd_env:
        return [sys.executable, fd_env] if fd_env.endswith('.py') else [fd_env]

    # 2. Check PATH for fast-downward or fast-downward.py
    for name in ('fast-downward', 'fast-downward.py'):
        if shutil.which(name):
            return [name]

    # 3. Common install locations
    candidates = [
        os.path.expanduser('~/downward/fast-downward.py'),
        '/usr/local/bin/fast-downward.py',
        'C:/downward/fast-downward.py',
    ]
    for path in candidates:
        if os.path.isfile(path):
            return [sys.executable, path]

    # 4. WSL fallback (Windows)
    if sys.platform == 'win32':
        return ['wsl', 'python3', '~/downward/fast-downward.py']

    raise FileNotFoundError(
        "Fast Downward not found. Set the FAST_DOWNWARD environment variable "
        "to the path of fast-downward.py, or install it on your PATH.\n"
        "Download from: https://github.com/aibasel/downward"
    )


_FD_CMD: list[str] | None = None


def get_fd_command() -> list[str]:
    global _FD_CMD
    if _FD_CMD is None:
        _FD_CMD = _find_fast_downward()
    return _FD_CMD


# -----------------------------------------------------------------------
# Core solver call
# -----------------------------------------------------------------------

def solve(
    domain_path: str,
    problem_path: str,
    timeout: int = 300,
    planner_profile: str = 'HSP',
) -> float:
    """
    Call Fast Downward with A* + LM-Cut heuristic (optimal search).

    Parameters
    ----------
    domain_path  : path to the (possibly augmented) domain PDDL file
    problem_path : path to the compiled problem PDDL file
    timeout      : wall-clock timeout in seconds (default 5 min)

    Returns
    -------
    float : optimal plan cost, or INF_COST if unsolvable / timeout
    """
    domain_path = os.path.abspath(domain_path)
    problem_path = os.path.abspath(problem_path)

    profile_key = planner_profile.upper()
    if profile_key not in PLANNER_PROFILES:
        raise ValueError(
            f"Unknown planner_profile '{planner_profile}'. "
            f"Valid options: {', '.join(PLANNER_PROFILES.keys())}"
        )

    # Fast Downward writes output files into CWD.
    # On Windows, TemporaryDirectory cleanup can race with process/file handles,
    # so we use explicit best-effort cleanup with retries.
    tmpdir = tempfile.mkdtemp(prefix='fd-run-')
    try:
        # fast-downward.py expects: <domain> <problem> <search/alias args>
        cmd = get_fd_command() + [
            domain_path,
            problem_path,
            *PLANNER_PROFILES[profile_key],
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return float(INF_COST)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Could not run Fast Downward: {exc}\n"
                "Install Fast Downward and set FAST_DOWNWARD env var."
            ) from exc
    finally:
        for _ in range(3):
            try:
                shutil.rmtree(tmpdir)
                break
            except OSError:
                time.sleep(0.1)
        else:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return _parse_cost(output)


def _parse_cost(output: str) -> float:
    """Extract plan cost from Fast Downward stdout."""
    # Fast Downward prints: "Plan cost: 5"
    match = re.search(r'Plan cost:\s*(\d+)', output)
    if match:
        return float(match.group(1))

    # Also handle: "Solution found." with cost in sas_plan
    # Some versions print "INFO     Cost of plan: 5"
    match = re.search(r'[Cc]ost\s+of\s+plan[:\s]+(\d+)', output)
    if match:
        return float(match.group(1))

    # No plan found
    if 'Solution found' in output:
        # Fallback: count actions in plan
        actions = re.findall(r'^\([a-z].*\)$', output, re.MULTILINE)
        if actions:
            return float(len(actions))

    return float(INF_COST)


# -----------------------------------------------------------------------
# Batch solving (compliant + non-compliant pair)
# -----------------------------------------------------------------------

def solve_pair(
    domain_obs_path: str,
    compliant_path: str,
    noncompliant_path: str,
    timeout: int = 300,
    planner_profile: str = 'HSP',
) -> tuple[float, float]:
    """
    Solve both the compliant and non-compliant planning problems.

    Returns (c_O, c_not_O) — the two optimal costs.
    """
    c_O = solve(
        domain_obs_path,
        compliant_path,
        timeout=timeout,
        planner_profile=planner_profile,
    )
    c_not_O = solve(
        domain_obs_path,
        noncompliant_path,
        timeout=timeout,
        planner_profile=planner_profile,
    )
    return c_O, c_not_O


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: solver.py domain.pddl problem.pddl [timeout_seconds]")
        sys.exit(1)
    domain = sys.argv[1]
    problem = sys.argv[2]
    tl = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    cost = solve(domain, problem, timeout=tl)
    print(f"Plan cost: {cost}")
