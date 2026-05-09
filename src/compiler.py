"""
compiler.py
-----------
Implements the PDDL domain/problem transformation from Ramírez & Geffner (AAAI-10).

Given:
  - domain.pddl        : original STRIPS domain
  - template.pddl      : problem template with <HYPOTHESIS> placeholder
  - hyps.dat           : one candidate goal per line (comma-separated PDDL atoms)
  - obs.dat            : comma-separated observed action instances

For each candidate goal G_i, produces two PDDL problem files:
  - compliant_<i>.pddl    : goal = G_i + p_last_obs  (plan must include observations)
  - noncompliant_<i>.pddl : goal = G_i + (not p_last_obs)
And one augmented domain file:
  - domain_obs.pddl       : original domain + observation-tracking fluents/effects
"""

import re
import os


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_obs(obs_path: str) -> list[str]:
    """Read obs.dat and return a list of ground action names (lower-case)."""
    with open(obs_path) as f:
        content = f.read().strip()
    # Each observation is a PDDL expression like (UNSTACK R P)
    # Split on ')' boundaries then clean up
    tokens = re.findall(r'\(([^)]+)\)', content)
    return [tok.strip().lower().replace(' ', '_') for tok in tokens]


def parse_hyps(hyps_path: str) -> list[list[str]]:
    """Read hyps.dat. Each line is a comma-separated list of PDDL atoms."""
    hyps = []
    with open(hyps_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            atoms = [a.strip() for a in line.split(',')]
            hyps.append(atoms)
    return hyps


def parse_real_hyp(real_hyp_path: str) -> list[str]:
    """Read real_hyp.dat — the true hidden goal (comma-separated atoms)."""
    with open(real_hyp_path) as f:
        line = f.read().strip()
    return [a.strip() for a in line.split(',')]


def read_template(template_path: str) -> str:
    with open(template_path) as f:
        return f.read()


def read_domain(domain_path: str) -> str:
    with open(domain_path) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Domain augmentation
# ---------------------------------------------------------------------------

def make_obs_fluent_name(obs_index: int) -> str:
    return f"obs_reached_{obs_index}"


def augment_domain(domain_text: str, obs_list: list[str]) -> str:
    """
    Add observation-tracking fluents and chain effects to the domain.

    For each observed action o_k (0-indexed):
      - Add Boolean fluent obs_reached_k
      - Modify the matching action: when o_{k-1} has been reached (or k==0),
        set obs_reached_k as an effect.

    The chaining ensures obs_reached_{n-1} is true only when the full
    observation sequence has been executed in order.
    """
    if not obs_list:
        return domain_text

    n = len(obs_list)

    # --- 1. Add new predicates ---
    new_preds = "\n".join(
        f"               (obs_reached_{i})" for i in range(n)
    )
    # Insert before closing of :predicates block
    domain_text = re.sub(
        r'(\(:predicates\s*(?:[^)]*\)\s*)*\))',
        lambda m: m.group(0)[:-1] + f"\n{new_preds}\n               )",
        domain_text,
        count=1,
        flags=re.DOTALL
    )

    # --- 2. Add conditional effects to each observed action ---
    for k, obs in enumerate(obs_list):
        # obs is like "unstack_r_p" — reconstruct action name and params
        parts = obs.split('_')
        action_name = parts[0]
        params = parts[1:]

        fluent_to_set = f"obs_reached_{k}"
        if k == 0:
            condition = None  # unconditional: just execute the action
        else:
            condition = f"obs_reached_{k - 1}"

        if condition is None:
            new_effect = f"(obs_reached_{k})"
        else:
            new_effect = f"(when ({condition}) (obs_reached_{k}))"

        # Find the action block and append to its :effect
        # We match the action by name (case-insensitive)
        pattern = re.compile(
            r'(\(:action\s+' + re.escape(action_name) + r'\b.*?:effect\s*\n?\s*)(.*?)\)\s*\)',
            re.IGNORECASE | re.DOTALL
        )

        def inject_effect(m, effect=new_effect):
            prefix = m.group(1)
            body = m.group(2).strip()
            # body is either "(and ...)" or a single atom
            if body.startswith('(and'):
                # Insert inside the existing (and ...)
                body = body[:-1] + f"\n                   {effect})"
            else:
                body = f"(and {body}\n                   {effect})"
            return prefix + body + "))"

        domain_text = pattern.sub(inject_effect, domain_text, count=1)

    return domain_text


# ---------------------------------------------------------------------------
# Problem file generation
# ---------------------------------------------------------------------------

def make_problem(template_text: str, goal_atoms: list[str], extra_goal: str | None) -> str:
    """
    Fill in the <HYPOTHESIS> placeholder in template.pddl.

    goal_atoms : list of PDDL atom strings, e.g. ["(CLEAR D)", "(ON D R)"]
    extra_goal : additional atom to append (or None)
    """
    goal_parts = list(goal_atoms)
    if extra_goal:
        goal_parts.append(extra_goal)

    goal_str = "\n".join(f"        {a}" for a in goal_parts)
    return template_text.replace('<HYPOTHESIS>', goal_str)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_problems(
    domain_path: str,
    template_path: str,
    hyps_path: str,
    obs_path: str,
    out_dir: str,
) -> dict:
    """
    Main entry point.

    Returns a dict with keys:
      'obs'          : list of observation strings
      'hyps'         : list of goal atom-lists
      'domain_obs'   : path to augmented domain file
      'compliant'    : list of paths to compliant problem files
      'noncompliant' : list of paths to non-compliant problem files
    """
    os.makedirs(out_dir, exist_ok=True)

    domain_text = read_domain(domain_path)
    template_text = read_template(template_path)
    obs_list = parse_obs(obs_path)
    hyps = parse_hyps(hyps_path)

    # Augment domain with observation fluents
    aug_domain = augment_domain(domain_text, obs_list)
    domain_obs_path = os.path.join(out_dir, 'domain_obs.pddl')
    with open(domain_obs_path, 'w') as f:
        f.write(aug_domain)

    compliant_paths = []
    noncompliant_paths = []

    if obs_list:
        last_fluent = f"(obs_reached_{len(obs_list) - 1})"
        last_fluent_neg = f"(not (obs_reached_{len(obs_list) - 1}))"
    else:
        last_fluent = None
        last_fluent_neg = None

    for i, goal_atoms in enumerate(hyps):
        # Compliant: plan must include the full observation sequence
        comp_text = make_problem(template_text, goal_atoms, last_fluent)
        comp_path = os.path.join(out_dir, f'problem_compliant_{i}.pddl')
        with open(comp_path, 'w') as f:
            f.write(comp_text)
        compliant_paths.append(comp_path)

        # Non-compliant: plan must NOT complete the observation sequence
        noncomp_text = make_problem(template_text, goal_atoms, last_fluent_neg)
        noncomp_path = os.path.join(out_dir, f'problem_noncompliant_{i}.pddl')
        with open(noncomp_path, 'w') as f:
            f.write(noncomp_text)
        noncompliant_paths.append(noncomp_path)

    return {
        'obs': obs_list,
        'hyps': hyps,
        'domain_obs': domain_obs_path,
        'compliant': compliant_paths,
        'noncompliant': noncompliant_paths,
    }


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 6:
        print("Usage: compiler.py domain.pddl template.pddl hyps.dat obs.dat out_dir/")
        sys.exit(1)
    result = compile_problems(*sys.argv[1:6])
    print(f"Compiled {len(result['hyps'])} hypotheses.")
    print(f"Obs sequence: {result['obs']}")
    print(f"Augmented domain: {result['domain_obs']}")
