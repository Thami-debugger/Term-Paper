#!/usr/bin/env python3
"""
Practical Test Script - Uses actual dataset archives
Extracts PDDL files and runs the monitoring agent on real data.
"""

import sys
import json
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

from plan_recognition_agent import PlanRecognitionAgent
from dataset_helper import DatasetHelper


def test_with_dataset_archive(
    archive_path: str,
    candidate_goals: list,
    observations: list,
    beta: float = 1.0,
    verbose: bool = True
) -> dict:
    """
    Test the agent with an actual archive from the dataset.
    
    Args:
        archive_path: Path to .tar.bz2 file in the dataset
        candidate_goals: List of possible goal names
        observations: List of observed action names
        beta: Boltzmann parameter
        verbose: Print progress
    """
    print("\n" + "="*70)
    print("PLAN RECOGNITION - DATASET ARCHIVE TEST")
    print("="*70)
    print(f"Archive: {Path(archive_path).name}")
    print(f"Candidate goals: {candidate_goals}")
    print(f"Observations: {observations}")
    
    # Extract archive
    print("\n[Step 1] Extracting archive...")
    extract_dir = tempfile.mkdtemp()
    extracted = DatasetHelper.extract_archive(archive_path, extract_dir)
    
    if 'domain' not in extracted:
        print("[ERROR] No domain.pddl found in archive")
        return {'error': 'No domain.pddl found'}
    
    if 'problem' not in extracted:
        print("[ERROR] No problem PDDL found in archive")
        return {'error': 'No problem PDDL found'}
    
    domain_file = str(extracted['domain'])
    problem_file = str(extracted['problem'])
    
    print(f"✓ Domain file: {domain_file}")
    print(f"✓ Problem file: {problem_file}")
    
    # Initialize agent
    print("\n[Step 2] Initializing agent...")
    agent = PlanRecognitionAgent(planner_path="fd", beta=beta, temp_dir="./pr_temp")
    
    # Check planner
    print("[Step 3] Checking planner availability...")
    if not agent.check_planner():
        print("\n[WARNING] Fast Downward not available!")
        print("To install: apt install fast-downward")
        print("Or build from: https://www.fast-downward.org/")
        return {'error': 'Planner not available'}
    
    # Run recognition
    print("\n[Step 4] Running goal recognition...")
    result = agent.recognize_goals(
        domain_path=domain_file,
        problem_path=problem_file,
        observations=observations,
        candidate_goals=candidate_goals,
        verbose=verbose
    )
    
    # Print results
    if 'error' not in result:
        agent.print_results(result)
    
    return result


def test_blocks_world_sample():
    """Test with a sample from the blocks-world dataset."""
    print("\n" + "#"*70)
    print("TEST 1: BLOCKS WORLD (50% Observations)")
    print("#"*70)
    
    # Find a blocks-world archive
    dataset_root = Path("goal-plan-recognition-dataset")
    archives = list(dataset_root.glob("blocks-world/50/*.tar.bz2"))
    
    if not archives:
        print("[ERROR] No blocks-world archives found")
        return None
    
    archive_path = str(archives[0])
    print(f"\nUsing: {Path(archive_path).name}")
    
    # Define test parameters
    candidate_goals = [
        "goal_abc",
        "goal_bca", 
        "goal_cab",
        "goal_acb",
        "goal_bac",
        "goal_cba"
    ]
    
    observations = [
        "pickup-a",
        "putdown-c",
        "pickup-b",
        "move-on-table",
    ]
    
    result = test_with_dataset_archive(
        archive_path,
        candidate_goals,
        observations,
        beta=1.0,
        verbose=True
    )
    
    return result


def test_campus_sample():
    """Test with a sample from the campus dataset."""
    print("\n" + "#"*70)
    print("TEST 2: CAMPUS DOMAIN (50% Observations)")
    print("#"*70)
    
    # Find a campus archive
    dataset_root = Path("goal-plan-recognition-dataset")
    archives = list(dataset_root.glob("campus/50/*.tar.bz2"))
    
    if not archives:
        print("[SKIP] No campus archives found")
        return None
    
    archive_path = str(archives[0])
    print(f"\nUsing: {Path(archive_path).name}")
    
    candidate_goals = [
        "attend_lecture",
        "study_library",
        "eat_lunch",
        "go_home"
    ]
    
    observations = [
        "move-to-lecture-hall",
        "sit-down",
        "take-notes"
    ]
    
    result = test_with_dataset_archive(
        archive_path,
        candidate_goals,
        observations,
        beta=0.5,
        verbose=True
    )
    
    return result


def list_available_archives():
    """Show what archives are available in the dataset."""
    print("\n" + "="*70)
    print("AVAILABLE ARCHIVES IN DATASET")
    print("="*70)
    
    dataset_root = Path("goal-plan-recognition-dataset")
    if not dataset_root.exists():
        print("[ERROR] Dataset folder not found!")
        return
    
    domains = sorted([d for d in dataset_root.iterdir() if d.is_dir() and not d.name.startswith('.') and not d.name.endswith('-noisy')])
    
    for domain_dir in domains:
        obs_levels = sorted([d for d in domain_dir.iterdir() if d.is_dir()])
        print(f"\n{domain_dir.name}:")
        for level_dir in obs_levels:
            archives = list(level_dir.glob("*.tar.bz2"))
            if archives:
                print(f"  {level_dir.name}%: {len(archives)} archives")
                print(f"    Example: {archives[0].name}")


def main():
    """Main test entry point."""
    print("\n" + "="*70)
    print("PLAN RECOGNITION AGENT - DATASET TEST")
    print("="*70)
    print("""
This script tests the monitoring agent using REAL DATA from
the goal-plan-recognition-dataset.

The agent will:
1. Extract PDDL files from tar.bz2 archives
2. Transform them according to the paper
3. Call Fast Downward planner
4. Score goals using Bayesian inference
5. Report results
""")
    
    # List available data
    list_available_archives()
    
    # Run tests
    print("\n" + "="*70)
    print("RUNNING TESTS")
    print("="*70)
    
    # Blocks World test
    result_bw = test_blocks_world_sample()
    
    # Campus test
    result_campus = test_campus_sample()
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    if result_bw and 'error' not in result_bw:
        print(f"✓ Blocks World test completed")
        print(f"  Top goal: {result_bw['top_goal']}")
        print(f"  Confidence: {result_bw['top_probability']:.4f}")
    else:
        print("✗ Blocks World test failed (planner may not be installed)")
    
    if result_campus and 'error' not in result_campus:
        print(f"✓ Campus test completed")
        print(f"  Top goal: {result_campus['top_goal']}")
        print(f"  Confidence: {result_campus['top_probability']:.4f}")
    else:
        print("✗ Campus test skipped (no archives or planner issue)")
    
    print("\n" + "="*70)
    print("NEXT STEPS FOR FULL REPRODUCIBILITY")
    print("="*70)
    print("""
To reproduce the full paper:

1. Install Fast Downward planner:
   apt install fast-downward

2. Modify this script to:
   - Loop through all observation levels (10%, 30%, 50%, 70%, 100%)
   - Test multiple problem instances from each level
   - Extract real observation sequences from archives
   - Record Q (goal accuracy) and S (ambiguity) metrics

3. Compare results to Table 1 in the paper:
   - BLOCK WORDS: Q=1.0, S=2.23 at 50%
   - CAMPUS: Q=1.0, S=1.0 at 50%
   - KITCHEN: Q=1.0, S=1.33 at 50%
   - etc.

4. Key insight: Adjust β parameter to match paper's results
   (Paper doesn't specify β, recommend trying 0.5-2.0)

Good luck with reproducibility!
""")


if __name__ == "__main__":
    main()
