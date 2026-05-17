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
from pathlib import PureWindowsPath

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

INF_COST = 1_000_000  # sentinel for unsolvable

PLANNER_PROFILES: dict[str, list[str]] = {
    'HSP': ['--search', 'astar(lmcut())'],
    'LAMA': ['--alias', 'seq-sat-lama-2011'],
    'GREEDY_LAMA': ['--alias', 'lama-first'],
}

WSL_DISTRO_EXCLUSIONS = {'docker-desktop', 'docker-desktop-data'}


def _list_wsl_distros() -> list[str]:
    result = subprocess.run(
        ['wsl', '-l', '-q'],
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line.replace('\x00', '').strip()
        for line in result.stdout.splitlines()
        if line.replace('\x00', '').strip()
    ]


def _probe_wsl_fast_downward(distro: str) -> list[str] | None:
    if distro.lower() in WSL_DISTRO_EXCLUSIONS:
        return None

    script_result = subprocess.run(
        [
            'wsl', '-d', distro, '--exec', 'sh', '-lc',
            'if command -v python3 >/dev/null 2>&1 && [ -f "$HOME/downward/fast-downward.py" ]; then '
            'printf "%s\n%s" python3 "$HOME/downward/fast-downward.py"; '
            'fi'
        ],
        capture_output=True,
        text=True,
    )
    if script_result.returncode != 0:
        return None

    lines = [line.strip() for line in script_result.stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        return None

    python_cmd, script_path = lines
    return ['wsl', '-d', distro, python_cmd, script_path]

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
        preferred_distro = os.environ.get('FAST_DOWNWARD_WSL_DISTRO')
        if preferred_distro:
            detected = _probe_wsl_fast_downward(preferred_distro)
            if detected is not None:
                return detected

        for distro in _list_wsl_distros():
            detected = _probe_wsl_fast_downward(distro)
            if detected is not None:
                return detected

    raise FileNotFoundError(
        "Fast Downward not found. Set the FAST_DOWNWARD environment variable "
        "to the path of fast-downward.py, or install it on your PATH.\n"
        "Download from: https://github.com/aibasel/downward"
    )


_FD_CMD: list[str] | None = None
_WSL_MOUNT_ROOT_CACHE: dict[tuple[str, str], str] = {}


def get_fd_command() -> list[str]:
    global _FD_CMD
    if _FD_CMD is None:
        _FD_CMD = _find_fast_downward()
    return _FD_CMD


def _is_wsl_command(cmd: list[str]) -> bool:
    return len(cmd) >= 1 and cmd[0].lower() == 'wsl'


def _resolve_wsl_mount_root(distro: str, drive: str) -> str:
    cache_key = (distro, drive)
    if cache_key in _WSL_MOUNT_ROOT_CACHE:
        return _WSL_MOUNT_ROOT_CACHE[cache_key]

    env_root = os.environ.get('WSL_MOUNT_ROOT')
    if env_root:
        root = env_root.rstrip('/')
        _WSL_MOUNT_ROOT_CACHE[cache_key] = root
        return root

    for candidate in ('/mnt/host', '/mnt'):
        probe_path = f"{candidate}/{drive}"
        probe = subprocess.run(
            ['wsl', '-d', distro, '--exec', 'test', '-d', probe_path],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            _WSL_MOUNT_ROOT_CACHE[cache_key] = candidate
            return candidate

    # Fallback keeps previous behavior if probing fails unexpectedly.
    _WSL_MOUNT_ROOT_CACHE[cache_key] = '/mnt/host'
    return '/mnt/host'


def _to_wsl_path(path: str, distro: str) -> str:
    win_path = PureWindowsPath(path)
    drive = win_path.drive.rstrip(':').lower()
    if not drive:
        raise RuntimeError(f"Expected an absolute Windows path, got: {path}")

    mount_root = _resolve_wsl_mount_root(distro, drive)
    relative_parts = [part for part in win_path.parts[1:] if part not in ('\\', '/')]
    return '/'.join([mount_root, drive, *relative_parts])


def _build_fd_command(
    fd_cmd: list[str],
    domain_path: str,
    problem_path: str,
    planner_args: list[str],
) -> list[str]:
    alias_mode = len(planner_args) >= 1 and planner_args[0] == '--alias'

    if not _is_wsl_command(fd_cmd):
        if alias_mode:
            return [*fd_cmd, *planner_args, domain_path, problem_path]
        return [*fd_cmd, domain_path, problem_path, *planner_args]

    if len(fd_cmd) < 5 or fd_cmd[1] != '-d':
        raise RuntimeError(f"Unexpected WSL Fast Downward command: {' '.join(fd_cmd)}")

    distro = fd_cmd[2]
    python_cmd = fd_cmd[3]
    wsl_script = fd_cmd[4]
    wsl_domain = _to_wsl_path(domain_path, distro)
    wsl_problem = _to_wsl_path(problem_path, distro)
    if alias_mode:
        return ['wsl', '-d', distro, '--exec', python_cmd, wsl_script, *planner_args, wsl_domain, wsl_problem]
    return ['wsl', '-d', distro, '--exec', python_cmd, wsl_script, wsl_domain, wsl_problem, *planner_args]


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
        cmd = _build_fd_command(
            get_fd_command(),
            domain_path,
            problem_path,
            PLANNER_PROFILES[profile_key],
        )

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

    if result.returncode != 0:
        output_lower = output.lower()
        unsolved_exit = result.returncode in (11, 12)
        unsolved_message = 'search stopped without finding a solution' in output_lower
        if unsolved_exit or unsolved_message:
            return float(INF_COST)

        raise RuntimeError(
            "Fast Downward exited with a non-zero status.\n"
            f"Command: {' '.join(cmd)}\n"
            f"Exit code: {result.returncode}\n"
            f"Output:\n{output.strip()}"
        )

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
