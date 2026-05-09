"""
generate_tables.py
------------------
Reads results/observable_all_results.json and prints LaTeX table rows
showing our reproduction results vs the paper's Table 1.

Usage:
    python report/generate_tables.py
"""

import json
import sys
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_FILE = os.path.join(ROOT, "results", "observable_all_results.json")

PAPER_TABLE1 = {
    # (domain, obs_level) -> {planner -> (T, Q, S)}
    ("blocks-world", 10):  {"HSP": (1184.23, 1.00, 6.00), "LAMA": (228.04, 0.75, 4.75), "GREEDY_LAMA": (52.79,  0.00, 1.67)},
    ("blocks-world", 30):  {"HSP": (1269.31, 1.00, 3.25), "LAMA": (239.59, 1.00, 3.00), "GREEDY_LAMA": (53.01,  0.50, 2.00)},
    ("blocks-world", 50):  {"HSP": (1423.05, 1.00, 2.23), "LAMA": (241.77, 1.00, 2.23), "GREEDY_LAMA": (53.00,  0.54, 1.23)},
    ("blocks-world", 70):  {"HSP": (1787.67, 1.00, 1.27), "LAMA": (241.53, 1.00, 1.27), "GREEDY_LAMA": (53.06,  0.73, 1.20)},
    ("blocks-world", 100): {"HSP": (2100.21, 1.00, 1.13), "LAMA": (241.51, 1.00, 1.13), "GREEDY_LAMA": (53.47,  0.73, 1.07)},
    ("easy-ipc-grid", 10):  {"HSP": (73.38,  0.75, 1.38), "LAMA": (22.15,  0.75, 1.38), "GREEDY_LAMA": (3.96,   0.75, 1.38)},
    ("easy-ipc-grid", 30):  {"HSP": (155.47, 1.00, 1.00), "LAMA": (64.63,  1.00, 1.00), "GREEDY_LAMA": (5.38,   1.00, 1.08)},
    ("easy-ipc-grid", 50):  {"HSP": (202.69, 1.00, 1.00), "LAMA": (71.77,  1.00, 1.00), "GREEDY_LAMA": (9.20,   1.00, 1.00)},
    ("easy-ipc-grid", 70):  {"HSP": (329.64, 1.00, 1.00), "LAMA": (92.84,  1.00, 1.00), "GREEDY_LAMA": (11.23,  1.00, 1.00)},
    ("easy-ipc-grid", 100): {"HSP": (435.60, 1.00, 1.00), "LAMA": (90.22,  1.00, 1.00), "GREEDY_LAMA": (13.07,  1.00, 1.00)},
    ("intrusion-detection", 10):  {"HSP": (26.29,  1.00, 1.80), "LAMA": (62.38,  1.00, 1.80), "GREEDY_LAMA": (3.69,  1.00, 2.20)},
    ("intrusion-detection", 30):  {"HSP": (73.08,  1.00, 1.13), "LAMA": (142.63, 1.00, 1.13), "GREEDY_LAMA": (4.09,  1.00, 1.13)},
    ("intrusion-detection", 50):  {"HSP": (103.58, 1.00, 1.00), "LAMA": (194.55, 1.00, 1.00), "GREEDY_LAMA": (4.44,  1.00, 1.00)},
    ("intrusion-detection", 70):  {"HSP": (188.44, 1.00, 1.00), "LAMA": (223.97, 1.00, 1.00), "GREEDY_LAMA": (4.96,  1.00, 1.00)},
    ("intrusion-detection", 100): {"HSP": (179.41, 1.00, 1.00), "LAMA": (224.96, 1.00, 1.00), "GREEDY_LAMA": (5.94,  1.00, 1.00)},
    ("logistics", 10):  {"HSP": (120.94,  0.90, 2.30), "LAMA": (215.32, 0.90, 2.30), "GREEDY_LAMA": (4.35,  0.60, 1.80)},
    ("logistics", 30):  {"HSP": (1071.91, 1.00, 1.07), "LAMA": (236.29, 1.00, 1.07), "GREEDY_LAMA": (4.55,  0.87, 1.13)},
    ("logistics", 50):  {"HSP": (813.36,  1.00, 1.20), "LAMA": (238.87, 1.00, 1.20), "GREEDY_LAMA": (5.37,  1.00, 1.20)},
    ("logistics", 70):  {"HSP": (606.87,  1.00, 1.00), "LAMA": (243.38, 1.00, 1.00), "GREEDY_LAMA": (6.29,  1.00, 1.00)},
    ("logistics", 100): {"HSP": (525.44,  1.00, 1.00), "LAMA": (247.04, 1.00, 1.00), "GREEDY_LAMA": (8.34,  1.00, 1.00)},
    ("campus", 10):  {"HSP": (0.67, 0.93, 1.33), "LAMA": (0.97, 0.93, 1.33), "GREEDY_LAMA": (0.74, 0.67, 1.27)},
    ("campus", 30):  {"HSP": (0.92, 1.00, 1.00), "LAMA": (1.13, 1.00, 1.00), "GREEDY_LAMA": (0.74, 0.80, 1.07)},
    ("campus", 50):  {"HSP": (1.11, 1.00, 1.00), "LAMA": (1.31, 1.00, 1.00), "GREEDY_LAMA": (0.77, 0.80, 1.13)},
    ("campus", 70):  {"HSP": (1.41, 1.00, 1.00), "LAMA": (1.63, 1.00, 1.00), "GREEDY_LAMA": (0.80, 0.80, 1.00)},
    ("campus", 100): {"HSP": (1.56, 1.00, 1.00), "LAMA": (1.84, 1.00, 1.00), "GREEDY_LAMA": (0.82, 1.00, 1.20)},
    ("kitchen", 10):  {"HSP": (77.85,  0.88, 1.25), "LAMA": (80.74, 0.88, 1.25), "GREEDY_LAMA": (1.55, 0.88, 1.25)},
    ("kitchen", 30):  {"HSP": (144.58, 0.93, 1.21), "LAMA": (80.82, 0.93, 1.21), "GREEDY_LAMA": (0.67, 0.93, 1.21)},
    ("kitchen", 50):  {"HSP": (218.51, 1.00, 1.33), "LAMA": (80.86, 1.00, 1.33), "GREEDY_LAMA": (0.71, 1.00, 1.27)},
    ("kitchen", 70):  {"HSP": (245.88, 1.00, 1.20), "LAMA": (80.86, 1.00, 1.20), "GREEDY_LAMA": (0.73, 1.00, 1.47)},
    ("kitchen", 100): {"HSP": (488.00, 1.00, 1.47), "LAMA": (81.16, 1.00, 1.40), "GREEDY_LAMA": (0.82, 1.00, 1.60)},
}

DOMAINS = [
    ("blocks-world",       "Block Words",         20),
    ("easy-ipc-grid",      "Easy IPC Grid",       7.5),
    ("intrusion-detection","Intrusion Detection", 15),
    ("logistics",          "Logistics",           10),
    ("campus",             "Campus",              2),
    ("kitchen",            "Kitchen",             3),
]
OBS_LEVELS = [10, 30, 50, 70, 100]
PLANNERS   = ["HSP", "LAMA", "GREEDY_LAMA"]


def load_our_results():
    if not os.path.exists(RESULTS_FILE):
        print(f"WARNING: {RESULTS_FILE} not found. Run experiments first.", file=sys.stderr)
        return {}
    with open(RESULTS_FILE) as f:
        raw = json.load(f)

    agg = {}
    for planner, pdata in raw.items():
        agg[planner] = {}
        for domain, entries in pdata.items():
            by_level = defaultdict(list)
            for e in entries:
                by_level[e["obs_level"]].append(e)
            agg[planner][domain] = {}
            for lvl, elist in by_level.items():
                agg[planner][domain][lvl] = {
                    "T": sum(e["runtime_sec"] for e in elist) / len(elist),
                    "Q": sum(e["Q"] for e in elist) / len(elist),
                    "S": sum(e["S"] for e in elist) / len(elist),
                    "n": len(elist),
                }
    return agg


def print_comparison_table(our):
    """Print a side-by-side comparison for each planner."""
    for planner in PLANNERS:
        planner_label = {"HSP": "HSP*_F (Optimal)", "LAMA": "LAMA (Anytime)", "GREEDY_LAMA": "Greedy LAMA"}[planner]
        print(f"\n{'='*70}")
        print(f"  {planner_label}")
        print(f"{'='*70}")
        header = f"{'Domain':<22} {'Obs%':>5} | {'Paper T':>8} {'Paper Q':>8} {'Paper S':>8} | {'Our T':>8} {'Our Q':>8} {'Our S':>8}"
        print(header)
        print("-" * len(header))
        for domain_key, domain_label, n_goals in DOMAINS:
            for lvl in OBS_LEVELS:
                paper = PAPER_TABLE1.get((domain_key, lvl), {}).get(planner)
                ours_d = our.get(planner, {}).get(domain_key, {}).get(lvl)
                p_T = f"{paper[0]:8.2f}" if paper else "       —"
                p_Q = f"{paper[1]:8.2f}" if paper else "       —"
                p_S = f"{paper[2]:8.2f}" if paper else "       —"
                o_T = f"{ours_d['T']:8.2f}" if ours_d else "       —"
                o_Q = f"{ours_d['Q']:8.2f}" if ours_d else "       —"
                o_S = f"{ours_d['S']:8.2f}" if ours_d else "       —"
                row_label = f"{domain_label:<22}" if lvl == 10 else f"{'':22}"
                print(f"{row_label} {lvl:5d} | {p_T} {p_Q} {p_S} | {o_T} {o_Q} {o_S}")
            print()


def main():
    our = load_our_results()
    print("Comparison: Paper Table 1 vs Our Results")
    print("(Our Q=1.0 and S=|G| for all entries due to planner returning inf costs)")
    print_comparison_table(our)

    # Also output JSON for potential LaTeX integration
    out_path = os.path.join(ROOT, "report", "comparison_data.json")
    output = {}
    for planner in PLANNERS:
        output[planner] = {}
        for domain_key, _, _ in DOMAINS:
            output[planner][domain_key] = {}
            for lvl in OBS_LEVELS:
                paper = PAPER_TABLE1.get((domain_key, lvl), {}).get(planner)
                ours_d = our.get(planner, {}).get(domain_key, {}).get(lvl)
                output[planner][domain_key][str(lvl)] = {
                    "paper": {"T": paper[0], "Q": paper[1], "S": paper[2]} if paper else None,
                    "ours":  ours_d,
                }
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull comparison data written to: {out_path}")


if __name__ == "__main__":
    main()
