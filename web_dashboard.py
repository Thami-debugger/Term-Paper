#!/usr/bin/env python3
"""
Local web dashboard for running and viewing reproduction experiments.

This server wraps observe_reproduction_agent.py so the full workflow can be
started from a browser and inspected in a single place.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from observe_reproduction_agent import (  # type: ignore
    DEFAULT_OBS_LEVELS,
    DEFAULT_PLANNERS,
    PLANNER_DISPLAY,
    _load_targets,
    run_observable_reproduction,
)

DATA_DIR = ROOT / "benchmarks" / "experiments"
RESULTS_DIR = ROOT / "results"
TARGETS_PATH = ROOT / "paper_targets.json"
COMBINED_RESULTS_PATH = RESULTS_DIR / "observable_all_results.json"

DEMO_STATE: dict[str, Any] = {
    "running": False,
    "output": "",
    "error": "",
    "started_at": None,
}
DEMO_LOCK = threading.Lock()

APP_STATE: dict[str, Any] = {
    "last_log": "No run yet.",
    "last_error": None,
    "last_run_at": None,
    "last_config": {
    "domains": [
      "blocks-world",
      "easy-ipc-grid",
      "logistics",
      "intrusion-detection",
      "campus",
      "kitchen",
    ],
        "obs_levels": [10, 30, 50, 70, 100],
        "planners": ["HSP", "LAMA", "GREEDY_LAMA"],
        "beta": 1.0,
        "timeout": 300,
        "max_instances": "",
        "compare_paper": True,
    },
}
STATE_LOCK = threading.Lock()

def available_domains() -> list[str]:
    if not DATA_DIR.exists():
        return []
    return sorted(
        p.name for p in DATA_DIR.iterdir()
        if p.is_dir() and not p.name.endswith("-noisy")
    )

def summaries_from_all_results(all_results: dict[str, dict[str, list[dict]]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for planner, domain_map in sorted(all_results.items()):
        for domain, rows in sorted(domain_map.items()):
            by_level: dict[int, list[dict]] = {}
            for row in rows:
                level = int(row["obs_level"])
                by_level.setdefault(level, []).append(row)
            for level, items in sorted(by_level.items()):
                n = len(items)
                t_mean = sum(float(item.get("runtime_sec", 0.0)) for item in items) / n
                q_mean = sum(float(item.get("Q", 0.0)) for item in items) / n
                s_mean = sum(float(item.get("S", 0.0)) for item in items) / n
                summaries.append(
                    {
                        "planner": planner,
                        "domain": domain,
                        "obs_level": level,
                        "n": n,
                        "t_mean": t_mean,
                        "q_mean": q_mean,
                        "s_mean": s_mean,
                    }
                )
    return summaries


def load_saved_results() -> dict[str, dict[str, list[dict]]]:
    if not COMBINED_RESULTS_PATH.exists():
        return {}
    with open(COMBINED_RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def build_matrix_rows(
    summaries: list[dict[str, Any]],
    targets: dict[str, dict[int, dict[str, dict[str, float]]]],
) -> list[dict[str, Any]]:
    lookup = {
        (row["domain"], int(row["obs_level"]), row["planner"]): row
        for row in summaries
    }

    domain_levels = set()
    for domain, levels in targets.items():
        for level in levels:
            domain_levels.add((domain, int(level)))
    for row in summaries:
        domain_levels.add((row["domain"], int(row["obs_level"])))

    rows: list[dict[str, Any]] = []
    for domain, level in sorted(domain_levels):
        planner_cells: dict[str, Any] = {}
        for planner in DEFAULT_PLANNERS:
            run_row = lookup.get((domain, level, planner))
            ref_row = targets.get(domain, {}).get(level, {}).get(PLANNER_DISPLAY[planner])
            planner_cells[planner] = {
                "run": run_row,
                "ref": ref_row,
            }
        rows.append({"domain": domain, "obs_level": level, "planners": planner_cells})
    return rows


def save_combined_results(all_results: dict[str, dict[str, list[dict]]]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(COMBINED_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)


def run_demo_job(form: dict[str, Any]) -> None:
    """Run assignment_demo.py in a subprocess and capture the output."""
    with DEMO_LOCK:
        if DEMO_STATE["running"]:
            return
        DEMO_STATE["running"] = True
        DEMO_STATE["output"] = ""
        DEMO_STATE["error"] = ""
        DEMO_STATE["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    domain = form.get("demo_domain", "blocks-world")
    obs_level = form.get("demo_obs_level", "10")
    planner = form.get("demo_planner", "HSP")
    beta = form.get("demo_beta", "1.0")
    timeout = form.get("demo_timeout", "120")
    max_inst = form.get("demo_max_instances", "1")
    skip_pipeline = form.get("demo_skip_pipeline", "0")

    cmd = [
        sys.executable,
        str(ROOT / "assignment_demo.py"),
        "--domain", str(domain),
        "--obs-level", str(obs_level),
        "--planner", str(planner),
        "--beta", str(beta),
        "--timeout", str(timeout),
        "--max-instances", str(max_inst),
    ]
    if skip_pipeline == "1":
        cmd.append("--skip-pipeline")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=600,
        )
        out = result.stdout + ("\n--- STDERR ---\n" + result.stderr if result.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        out = "[TIMEOUT] Demo exceeded 600 seconds."
    except Exception as exc:
        out = f"[ERROR] {exc}"

    with DEMO_LOCK:
        DEMO_STATE["running"] = False
        DEMO_STATE["output"] = out

def run_job(form: dict[str, Any]) -> None:
    domains = form["domains"]
    obs_levels = [int(v) for v in form["obs_levels"]]
    planners = form["planners"]
    beta = float(form["beta"])
    timeout = int(form["timeout"])
    max_instances = form["max_instances"]
    max_instances_value = int(max_instances) if str(max_instances).strip() else None

    log_stream = io.StringIO()
    all_results: dict[str, dict[str, list[dict]]] = {}

    try:
        with contextlib.redirect_stdout(log_stream):
            for planner in planners:
                planner_results, _planner_summaries = run_observable_reproduction(
                    planner_profile=planner,
                    data_dir=DATA_DIR,
                    domains=domains,
                    obs_levels=sorted(obs_levels),
                    beta=beta,
                    timeout=timeout,
                    out_dir=RESULTS_DIR,
                    max_instances=max_instances_value,
                    verbose=False,
                )
                all_results[planner] = planner_results
        save_combined_results(all_results)
        error = None
    except Exception as exc:
        error = str(exc)

    with STATE_LOCK:
        APP_STATE["last_log"] = log_stream.getvalue() or "Run completed without log output."
        APP_STATE["last_error"] = error
        APP_STATE["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        APP_STATE["last_config"] = {
            "domains": domains,
            "obs_levels": obs_levels,
            "planners": planners,
            "beta": beta,
            "timeout": timeout,
            "max_instances": max_instances,
            "compare_paper": form["compare_paper"],
        }


def parse_form_data(raw_body: bytes) -> dict[str, Any]:
    parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
    domains = parsed.get("domains", []) or ["blocks-world", "easy-ipc-grid"]
    obs_levels = parsed.get("obs_levels", []) or [str(v) for v in DEFAULT_OBS_LEVELS]
    planners = [p.upper() for p in parsed.get("planners", [])] or DEFAULT_PLANNERS
    return {
        "domains": domains,
        "obs_levels": obs_levels,
        "planners": planners,
        "beta": parsed.get("beta", ["1.0"])[0],
        "timeout": parsed.get("timeout", ["300"])[0],
        "max_instances": parsed.get("max_instances", [""])[0],
        "compare_paper": "compare_paper" in parsed,
        # demo fields
        "demo_domain": parsed.get("demo_domain", ["blocks-world"])[0],
        "demo_obs_level": parsed.get("demo_obs_level", ["10"])[0],
        "demo_planner": parsed.get("demo_planner", ["HSP"])[0],
        "demo_beta": parsed.get("demo_beta", ["1.0"])[0],
        "demo_timeout": parsed.get("demo_timeout", ["120"])[0],
        "demo_max_instances": parsed.get("demo_max_instances", ["1"])[0],
        "demo_skip_pipeline": parsed.get("demo_skip_pipeline", ["0"])[0],
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/results":
            self._send_json(load_saved_results())
            return
        if parsed.path == "/api/demo-status":
            with DEMO_LOCK:
                self._send_json(dict(DEMO_STATE))
            return
        if parsed.path == "/":
            self._send_html(render_page())
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        if self.path == "/api/demo":
            content_length = int(self.headers.get("Content-Length", "0"))
            form = parse_form_data(self.rfile.read(content_length))
            threading.Thread(
                target=run_demo_job, args=(form,), daemon=True
            ).start()
            self._send_json({"started": True})
            return

        if self.path != "/run":
            self.send_error(404, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        form = parse_form_data(self.rfile.read(content_length))
        run_job(form)
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: Any) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def checkbox(name: str, value: str, label: str, selected_values: list[str]) -> str:
    checked = "checked" if value in selected_values else ""
    return (
        f'<label class="chip"><input type="checkbox" name="{html.escape(name)}" '
        f'value="{html.escape(value)}" {checked}> <span>{html.escape(label)}</span></label>'
    )


def render_page() -> str:
    with STATE_LOCK:
        state = dict(APP_STATE)

    all_results = load_saved_results()
    summaries = summaries_from_all_results(all_results)
    targets = _load_targets(str(TARGETS_PATH)) if TARGETS_PATH.exists() else {}
    matrix_rows = build_matrix_rows(summaries, targets)
    domains = available_domains()
    config = state["last_config"]

    compare_section = render_comparison_matrix(matrix_rows) if config.get("compare_paper") else ""
    summary_section = render_summary_table(summaries)
    log_text = html.escape(state.get("last_log") or "")
    error_html = ""
    if state.get("last_error"):
        error_html = f'<div class="error">Last run error: {html.escape(state["last_error"])}</div>'

    domain_checks = "".join(
        checkbox("domains", domain, domain, config.get("domains", []))
        for domain in domains
    )
    obs_checks = "".join(
        checkbox("obs_levels", str(level), f"{level}%", [str(v) for v in config.get("obs_levels", [])])
        for level in DEFAULT_OBS_LEVELS
    )
    planner_checks = "".join(
        checkbox("planners", planner, PLANNER_DISPLAY[planner], config.get("planners", []))
        for planner in DEFAULT_PLANNERS
    )
    compare_checked = "checked" if config.get("compare_paper", True) else ""
    last_run_at = html.escape(str(state.get("last_run_at") or "Never"))
    demo_domain_options = "".join(
        f'<option value="{html.escape(d)}">{html.escape(d)}</option>' for d in domains
    ) or '<option value="blocks-world">blocks-world</option>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Plan Recognition Reproduction Dashboard</title>
  <style>
    :root {{
      --bg: #f6f1e8;
      --panel: #fffaf2;
      --ink: #1f2933;
      --muted: #5c6b73;
      --line: #d8c8ae;
      --accent: #0f766e;
      --accent-2: #b45309;
      --good: #166534;
      --bad: #b91c1c;
      --shadow: 0 18px 48px rgba(84, 58, 20, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Palatino Linotype", serif;
      background:
        radial-gradient(circle at top right, rgba(180,83,9,0.12), transparent 25%),
        radial-gradient(circle at left center, rgba(15,118,110,0.12), transparent 30%),
        var(--bg);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(15,118,110,0.96), rgba(180,83,9,0.92));
      color: white;
      border-radius: 24px;
      padding: 28px;
      box-shadow: var(--shadow);
    }}
    .hero h1 {{ margin: 0 0 8px; font-size: clamp(2rem, 4vw, 3.5rem); }}
    .hero p {{ margin: 0; max-width: 70ch; line-height: 1.5; }}
    .grid {{
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 24px;
      margin-top: 24px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 20px;
      box-shadow: var(--shadow);
    }}
    h2 {{ margin-top: 0; font-size: 1.4rem; }}
    .sub {{ color: var(--muted); font-size: 0.95rem; margin-bottom: 12px; }}
    .group {{ margin-bottom: 18px; }}
    .label {{ font-weight: 700; margin-bottom: 8px; display: block; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--line);
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.85);
      font-size: 0.95rem;
    }}
    .fields {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
    input[type="number"], input[type="text"] {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 1rem;
      background: white;
    }}
    button {{
      width: 100%;
      border: 0;
      border-radius: 16px;
      padding: 14px 18px;
      background: linear-gradient(135deg, var(--accent), #155e75);
      color: white;
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
    }}
    .meta {{ display: flex; gap: 14px; flex-wrap: wrap; color: var(--muted); font-size: 0.92rem; }}
    .error {{
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(185, 28, 28, 0.08);
      color: var(--bad);
      border: 1px solid rgba(185, 28, 28, 0.2);
    }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 18px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 980px; }}
    th, td {{ padding: 12px 10px; border-bottom: 1px solid var(--line); text-align: center; }}
    th {{ background: rgba(15,118,110,0.08); font-size: 0.92rem; }}
    td:first-child, td:nth-child(2) {{ text-align: left; }}
    .planner-head {{ background: rgba(180,83,9,0.12); }}
    .delta-good {{ color: var(--good); font-weight: 700; }}
    .delta-bad {{ color: var(--bad); font-weight: 700; }}
    pre {{
      margin: 0;
      padding: 16px;
      background: #1f2933;
      color: #f8fafc;
      border-radius: 18px;
      overflow-x: auto;
      max-height: 420px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .empty {{ color: var(--muted); font-style: italic; }}
    .demo-terminal {{
      margin: 0;
      padding: 16px;
      background: #0d1117;
      color: #e6edf3;
      border-radius: 18px;
      overflow-y: auto;
      max-height: 620px;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: 'Courier New', Courier, monospace;
      font-size: 0.88rem;
      line-height: 1.55;
    }}
    .demo-form-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; align-items: flex-end; }}
    .demo-form-row label {{ display: flex; flex-direction: column; gap: 4px; font-size: 0.92rem; font-weight: 700; }}
    .demo-form-row select {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 9px 12px;
      font-size: 0.95rem;
      background: white;
    }}
    .demo-form-row input[type=number], .demo-form-row input[type=text] {{ width: 90px; }}
    .component-h {{ color: #79c0ff; font-weight: bold; }}
    .component-sub {{ color: #a5d6ff; }}
    .component-ok {{ color: #56d364; }}
    .component-warn {{ color: #e3b341; }}
    #demo-spinner {{ display: none; color: #e3b341; }}
    @media (max-width: 980px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .fields {{ grid-template-columns: 1fr; }}
            .cards {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Plan Recognition Reproduction Dashboard</h1>
      <p>Run the reproduction pipeline, inspect the paper-style metrics, and show the four assignment components from one focused submission page.</p>
    </section>

    <div class="grid">
      <section class="panel">
        <h2>Run Experiment</h2>
        <div class="sub">Last run: {last_run_at}</div>
        <form method="post" action="/run">
          <div class="group">
            <span class="label">Domains</span>
            <div class="chips">{domain_checks}</div>
          </div>
          <div class="group">
            <span class="label">Observation Levels</span>
            <div class="chips">{obs_checks}</div>
          </div>
          <div class="group">
            <span class="label">Planners</span>
            <div class="chips">{planner_checks}</div>
          </div>
          <div class="group fields">
            <label>
              <span class="label">Beta</span>
              <input type="text" name="beta" value="{html.escape(str(config.get('beta', 1.0)))}">
            </label>
            <label>
              <span class="label">Timeout (seconds)</span>
              <input type="number" name="timeout" value="{html.escape(str(config.get('timeout', 300)))}">
            </label>
            <label>
              <span class="label">Max Instances</span>
              <input type="number" name="max_instances" value="{html.escape(str(config.get('max_instances', '')))}" placeholder="blank = all">
            </label>
            <label class="chip" style="align-self:end; justify-content:center;">
              <input type="checkbox" name="compare_paper" {compare_checked}>
              <span>Compare against paper targets</span>
            </label>
          </div>
          <button type="submit">Run And Refresh Dashboard</button>
        </form>
        {error_html}
      </section>

      <section class="panel">
        <h2>Overview</h2>
        <div class="meta">
          <span>Results file: {html.escape(str(COMBINED_RESULTS_PATH.name))}</span>
          <span>Targets file: {html.escape(str(TARGETS_PATH.name))}</span>
          <span>API: /api/results</span>
        </div>
        {summary_section}
      </section>
    </div>

    <section class="panel" style="margin-top:24px;">
      <h2>Paper-Style Comparison Matrix</h2>
      <div class="sub">Each planner shows your run values and the paper reference in the same row.</div>
      {compare_section}
    </section>

    <section class="panel" style="margin-top:24px;">
      <h2>Run Log</h2>
      <pre>{log_text}</pre>
    </section>

    <section class="panel" style="margin-top:24px;" id="demo-section">
      <h2>Step-by-Step Component Demo</h2>
      <div class="sub">
        Runs <strong>assignment_demo.py</strong> live and shows each of the four
        assignment components: PDDL Compiler &rarr; Planner Integration &rarr;
        Bayesian Scoring &rarr; Evaluation Pipeline.
      </div>
      <div class="demo-form-row">
        <label>Domain
          <select id="d-domain">
            {demo_domain_options}
          </select>
        </label>
        <label>Obs Level
          <select id="d-obs">
            <option value="10">10%</option>
            <option value="30">30%</option>
            <option value="50">50%</option>
            <option value="70">70%</option>
            <option value="100">100%</option>
          </select>
        </label>
        <label>Planner
          <select id="d-planner">
            <option value="HSP">HSP (A*+LM-Cut)</option>
            <option value="LAMA">LAMA</option>
            <option value="GREEDY_LAMA">Greedy LAMA</option>
          </select>
        </label>
        <label>Beta
          <input type="text" id="d-beta" value="1.0" style="width:70px;">
        </label>
        <label>Timeout (s)
          <input type="number" id="d-timeout" value="120" style="width:90px;">
        </label>
        <label>Max Instances
          <input type="number" id="d-maxinst" value="1" style="width:90px;">
        </label>
        <label style="flex-direction:row;align-items:center;gap:8px;font-weight:normal;">
          <input type="checkbox" id="d-skippipe">
          <span>Skip pipeline (Components 1-3 only)</span>
        </label>
      </div>
      <button onclick="runDemo()" style="width:auto;padding:12px 28px;margin-bottom:16px;">
        Run Component Demo
      </button>
      <span id="demo-spinner">&#9654; Running... (check output below, auto-refreshes)</span>
      <pre class="demo-terminal" id="demo-out">Click &quot;Run Component Demo&quot; to start.

The demo will show:
  [Component 1] PDDL Compiler  -- src/compiler.py
    Reads domain.pddl + obs.dat + hyps.dat
    Generates compliant_i.pddl and noncompliant_i.pddl per hypothesis

  [Component 2] Planner Integration  -- src/solver.py
    Calls Fast Downward for each compiled problem pair
    Returns c(G,O) and c(G,~O) costs

  [Component 3] Bayesian Scoring  -- src/scoring.py
    Computes Boltzmann likelihoods and Bayes posterior
    Reports Q (accuracy) and S (specificity)

  [Component 4] Evaluation Pipeline  -- src/evaluate.py
    Iterates over all benchmark archives at the chosen obs level
    Aggregates Q +- std and S +- std  (Table 1 reproduction)
</pre>
    </section>
  </div>

<script>
var _demoPolling = null;

function runDemo() {{
  var body = new URLSearchParams();
  body.append('demo_domain',        document.getElementById('d-domain').value);
  body.append('demo_obs_level',     document.getElementById('d-obs').value);
  body.append('demo_planner',       document.getElementById('d-planner').value);
  body.append('demo_beta',          document.getElementById('d-beta').value);
  body.append('demo_timeout',       document.getElementById('d-timeout').value);
  body.append('demo_max_instances', document.getElementById('d-maxinst').value);
  body.append('demo_skip_pipeline', document.getElementById('d-skippipe').checked ? '1' : '0');

  document.getElementById('demo-out').textContent = 'Starting demo...';
  document.getElementById('demo-spinner').style.display = 'inline';

  fetch('/api/demo', {{method:'POST', body: body.toString(),
    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}}
  }}).then(function() {{
    if (_demoPolling) clearInterval(_demoPolling);
    _demoPolling = setInterval(pollDemoStatus, 1500);
  }});
}}

function pollDemoStatus() {{
  fetch('/api/demo-status').then(function(r) {{ return r.json(); }}).then(function(s) {{
    var el = document.getElementById('demo-out');
    if (s.output) {{
      el.textContent = s.output;
      el.scrollTop = el.scrollHeight;
    }}
    if (!s.running) {{
      clearInterval(_demoPolling);
      _demoPolling = null;
      document.getElementById('demo-spinner').style.display = 'none';
    }}
  }});
}}
</script>
</body>
</html>
"""


def render_summary_table(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return '<div class="empty">No saved results yet. Run the experiment from the left panel.</div>'

    rows = []
    for row in sorted(summaries, key=lambda x: (x["planner"], x["domain"], x["obs_level"])):
        rows.append(
            "<tr>"
            f"<td>{html.escape(PLANNER_DISPLAY.get(row['planner'], row['planner']))}</td>"
            f"<td>{html.escape(row['domain'])}</td>"
            f"<td>{row['obs_level']}</td>"
            f"<td>{row['n']}</td>"
            f"<td>{row['t_mean']:.2f}</td>"
            f"<td>{row['q_mean']:.3f}</td>"
            f"<td>{row['s_mean']:.3f}</td>"
            "</tr>"
        )

    return (
        '<div class="table-wrap"><table>'
        '<thead><tr><th>Planner</th><th>Domain</th><th>O</th><th>N</th><th>T(s)</th><th>Q</th><th>S</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def delta_cell(value: float | None) -> str:
    if value is None:
        return '<span class="empty">-</span>'
    css = "delta-good" if abs(value) < 0.05 else "delta-bad"
    return f'<span class="{css}">{value:+.3f}</span>'


def metric_cell(run: dict[str, Any] | None, ref: dict[str, float] | None, metric: str) -> str:
    run_value = None if run is None else run.get({"T": "t_mean", "Q": "q_mean", "S": "s_mean"}[metric])
    ref_value = None if ref is None else ref.get(metric)
    run_text = "-" if run_value is None else (f"{float(run_value):.2f}" if metric == "T" else f"{float(run_value):.3f}")
    ref_text = "-" if ref_value is None else (f"{float(ref_value):.2f}" if metric == "T" else f"{float(ref_value):.3f}")
    return f"<div>{run_text}</div><div class='sub'>ref {ref_text}</div>"


def render_comparison_matrix(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<div class="empty">No comparison data yet. Run the experiment first.</div>'

    header_top = [
        '<tr><th rowspan="2">Domain</th><th rowspan="2">O</th>',
    ]
    header_bottom = []
    for planner in DEFAULT_PLANNERS:
        header_top.append(f'<th class="planner-head" colspan="5">{html.escape(PLANNER_DISPLAY[planner])}</th>')
        header_bottom.extend([
            '<th>T</th>', '<th>Q</th>', '<th>S</th>', '<th>dQ</th>', '<th>dS</th>'
        ])
    header_top.append('</tr>')

    body_rows = []
    for row in rows:
        parts = [f'<tr><td>{html.escape(row["domain"])}</td><td>{row["obs_level"]}</td>']
        for planner in DEFAULT_PLANNERS:
            run = row["planners"][planner]["run"]
            ref = row["planners"][planner]["ref"]
            dq = None
            ds = None
            if run and ref:
                dq = float(run["q_mean"]) - float(ref["Q"])
                ds = float(run["s_mean"]) - float(ref["S"])
            parts.append(f'<td>{metric_cell(run, ref, "T")}</td>')
            parts.append(f'<td>{metric_cell(run, ref, "Q")}</td>')
            parts.append(f'<td>{metric_cell(run, ref, "S")}</td>')
            parts.append(f'<td>{delta_cell(dq)}</td>')
            parts.append(f'<td>{delta_cell(ds)}</td>')
        parts.append('</tr>')
        body_rows.append("".join(parts))

    return (
        '<div class="table-wrap"><table>'
        f'<thead>{"".join(header_top)}<tr>{"".join(header_bottom)}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the reproduction web dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Dashboard running at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
