#!/usr/bin/env python3
"""
Interactive Demo: Plan Recognition Agent on Goal-Plan Recognition Dataset
Tests the agent with sample data from blocks-world and campus domains.
"""

import sys
import json
from pathlib import Path
from typing import List

from plan_recognition_agent import PlanRecognitionAgent


def demo_blocks_world():
    """Demo with Blocks World domain."""
    print("\n" + "="*70)
    print("DEMO 1: BLOCKS WORLD")
    print("="*70)
    print("Testing with blocks-world domain from the dataset.")
    print("This domain involves recognizing which word is being spelled.")
    
    # Initialize agent
    agent = PlanRecognitionAgent(planner_path="fd", beta=1.0)
    
    # Check planner
    if not agent.check_planner():
        print("\n[SKIP] Planner not available. Install Fast Downward to continue.")
        return None
    
    # For this demo, we would need:
    # 1. Load a blocks-world domain PDDL file
    # 2. Define candidate goals (the words)
    # 3. Create a synthetic observation sequence
    
    print("\n[Note] Full Blocks World demo requires extracting PDDL from tar archives.")
    print("       These are packed in: goal-plan-recognition-dataset/blocks-world/*/")
    print("       Each archive contains domain and problem files.")
    
    return agent


def demo_campus():
    """Demo with Campus domain."""
    print("\n" + "="*70)
    print("DEMO 2: CAMPUS DOMAIN")
    print("="*70)
    print("Testing with campus domain from the dataset.")
    print("This domain involves recognizing student activities from location changes.")
    
    # Initialize agent
    agent = PlanRecognitionAgent(planner_path="fd", beta=0.5)
    
    # Check planner
    if not agent.check_planner():
        print("\n[SKIP] Planner not available.")
        return None
    
    print("\n[Note] Campus demo requires extracting PDDL from tar archives.")
    print("       These are packed in: goal-plan-recognition-dataset/campus/*/")
    
    return agent


def list_available_data():
    """List available data in the dataset."""
    print("\n" + "="*70)
    print("AVAILABLE DATA")
    print("="*70)
    
    dataset_root = Path("goal-plan-recognition-dataset")
    if not dataset_root.exists():
        print("[ERROR] Dataset root not found. Run from the project directory.")
        return
    
    domains = [d for d in dataset_root.iterdir() if d.is_dir() and not d.name.startswith('.')]
    domains = sorted([d for d in domains if not d.name.endswith('-noisy')])
    
    for domain in domains:
        problems = list(domain.glob("*/*.tar.bz2"))
        if problems:
            print(f"\n{domain.name:30s} - {len(problems)} archives")
            # Show percentage levels
            levels = set()
            for p in problems:
                parent = p.parent.name
                levels.add(parent)
            levels = sorted(levels)
            print(f"  Observation levels: {', '.join(levels)}")


def main():
    """Main demo entry point."""
    print("\n" + "="*70)
    print("PLAN RECOGNITION AGENT - INTERACTIVE DEMO")
    print("="*70)
    print("\nThis script demonstrates the goal recognition agent")
    print("using the goal-plan-recognition-dataset.")
    
    print("\nSetup Summary:")
    print("✓ Deleted unused domain folders (keeping only blocks-world and campus)")
    print("✓ Created PDDL transformation module")
    print("✓ Created planner integration (Fast Downward)")
    print("✓ Created Bayesian scoring module")
    print("✓ Created monitoring agent")
    
    # List available data
    list_available_data()
    
    print("\n" + "="*70)
    print("RUNNING DEMOS")
    print("="*70)
    
    # Run demos
    agent_bw = demo_blocks_world()
    agent_campus = demo_campus()
    
    print("\n" + "="*70)
    print("NEXT STEPS")
    print("="*70)
    print("""
To run the full reproducibility study:

1. Install Fast Downward:
   - On Ubuntu/Debian: apt install fast-downward
   - Or download from: https://www.fast-downward.org/

2. Extract sample data from tar archives:
   - Use: tar -xjf blocks-world/10/block-words_p01_hyp-0_10_0.tar.bz2
   - This gives you domain.pddl and problem files

3. Modify this script to:
   - Load the extracted PDDL files
   - Define your candidate goals
   - Create observation sequences by sampling plan prefixes
   - Run agent.recognize_goals()
   - Print and analyze results

4. For each domain (blocks-world, campus):
   - Test with 10%, 30%, 50%, 70%, 100% observations
   - Calculate Q (how often hidden goal ranks highest)
   - Calculate S (average number of tied top goals)
   - Compare to paper's Table 1 results

Example usage:
    agent = PlanRecognitionAgent(planner_path="fd", beta=1.0)
    result = agent.recognize_goals(
        domain_path="domain.pddl",
        problem_path="problem.pddl",
        observations=["move", "pickup", "putdown"],
        candidate_goals=["tower_abc", "tower_bca", "tower_cab"],
        verbose=True
    )
    agent.print_results(result)
    agent.save_results(result, "results.json")
    """)
    
    print("="*70)


if __name__ == "__main__":
    main()
