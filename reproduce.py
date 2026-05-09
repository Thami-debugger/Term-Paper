#!/usr/bin/env python3
"""Single entry point for reproducing the paper locally.

This wrapper keeps the repository focused on three supported workflows:

1. `run`  - paper-style reproduction across domains/observation levels
2. `demo` - step-by-step demonstration of the four assignment components
3. `web`  - local dashboard for running and viewing both workflows

Examples
--------
python reproduce.py run --domains blocks-world easy-ipc-grid --obs-levels 10 30 50
python reproduce.py demo --domain blocks-world --obs-level 10 --skip-pipeline
python reproduce.py web --no-browser
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _run_script(script_name: str, forwarded_args: list[str]) -> int:
    cmd = [sys.executable, str(ROOT / script_name), *forwarded_args]
    completed = subprocess.run(cmd, cwd=str(ROOT))
    return int(completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the supported paper-reproduction workflows from one entry point.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run the paper-style reproduction runner.",
    )
    run_parser.add_argument("args", nargs=argparse.REMAINDER)

    demo_parser = subparsers.add_parser(
        "demo",
        help="Run the step-by-step assignment component demo.",
    )
    demo_parser.add_argument("args", nargs=argparse.REMAINDER)

    web_parser = subparsers.add_parser(
        "web",
        help="Start the local reproduction dashboard.",
    )
    web_parser.add_argument("args", nargs=argparse.REMAINDER)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        return _run_script("observe_reproduction_agent.py", args.args)
    if args.command == "demo":
        return _run_script("assignment_demo.py", args.args)
    if args.command == "web":
        return _run_script("web_dashboard.py", args.args)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())