"""
Plan Recognition Monitoring Agent
Interactive interface for testing goal recognition on the dataset.
"""

import json
import tarfile
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple
import sys
import traceback

from pddl_transformer import PDDLTransformer
from planner_interface import PlannerInterface, CostComputer
from bayesian_scorer import BayesianScorer


class PlanRecognitionAgent:
    """Main agent for goal recognition experiments."""
    
    def __init__(
        self,
        planner_path: str = "fd",
        beta: float = 1.0,
        temp_dir: str = "./pr_temp"
    ):
        """
        Args:
            planner_path: Path to planner executable
            beta: Boltzmann parameter for scoring
            temp_dir: Temporary directory for transformed files
        """
        self.planner = PlannerInterface(planner_path)
        self.scorer = BayesianScorer(beta=beta)
        self.cost_computer = CostComputer(self.planner)
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        
        self.results_history = []
    
    def extract_tar_archive(self, tar_path: str, extract_to: str = None) -> Dict[str, str]:
        """Extracts tar.bz2 archive and returns file paths."""
        if extract_to is None:
            extract_to = tempfile.mkdtemp()
        
        extract_path = Path(extract_to)
        extract_path.mkdir(parents=True, exist_ok=True)
        
        files = {}
        with tarfile.open(tar_path, 'r:bz2') as tar:
            tar.extractall(extract_path)
            
            # Find PDDL files
            for file in extract_path.rglob('*.pddl'):
                if 'domain' in file.name.lower():
                    files['domain'] = str(file)
                elif 'problem' in file.name.lower():
                    files['problem'] = str(file)
        
        return files
    
    def load_pddl_files(self, domain_path: str, problem_path: str) -> Tuple[str, str]:
        """Load PDDL files from disk."""
        with open(domain_path, 'r') as f:
            domain = f.read()
        with open(problem_path, 'r') as f:
            problem = f.read()
        return domain, problem
    
    def recognize_goals(
        self,
        domain_path: str,
        problem_path: str,
        observations: List[str],
        candidate_goals: List[str],
        verbose: bool = True
    ) -> Dict:
        """
        Main recognition pipeline.
        
        Args:
            domain_path: Path to domain PDDL file
            problem_path: Path to problem PDDL file
            observations: List of observed action names
            candidate_goals: List of possible goal names
            verbose: Print progress
        
        Returns:
            Dict with recognition results including posteriors and rankings
        """
        if verbose:
            print("\n" + "="*70)
            print("PLAN RECOGNITION AGENT - MONITORING")
            print("="*70)
            print(f"Domain file: {domain_path}")
            print(f"Problem file: {problem_path}")
            print(f"Observations: {observations}")
            print(f"Candidate goals: {candidate_goals}")
        
        try:
            # Load PDDL files
            domain, problem = self.load_pddl_files(domain_path, problem_path)
            
            # Transform domain
            if verbose:
                print("\n[Agent] Transforming domain...")
            transformer = PDDLTransformer(domain, problem, observations)
            transformed_domain = transformer.transform_domain()
            
            # Compute costs for each goal
            all_costs = {}
            for goal in candidate_goals:
                if verbose:
                    print(f"\n[Agent] Processing goal: {goal}")
                
                # Create compliant and non-compliant problems
                compliant_prob = transformer.create_compliant_problem(goal)
                noncompliant_prob = transformer.create_noncompliant_problem(goal)
                
                # Save transformed files
                run_dir = self.temp_dir / goal
                run_dir.mkdir(exist_ok=True)
                
                domain_file = run_dir / "domain.pddl"
                comp_file = run_dir / "problem_comp.pddl"
                noncomp_file = run_dir / "problem_noncomp.pddl"
                
                domain_file.write_text(transformed_domain)
                comp_file.write_text(compliant_prob)
                noncomp_file.write_text(noncompliant_prob)
                
                # Compute costs
                costs = self.cost_computer.compute_costs(
                    str(domain_file),
                    str(comp_file),
                    str(noncomp_file),
                    goal,
                    verbose=verbose
                )
                all_costs[goal] = costs
            
            # Score goals using Bayesian inference
            if verbose:
                print("\n" + "-"*70)
            posteriors, cost_diffs = self.scorer.score_goals(all_costs, verbose=verbose)
            
            # Rank goals
            ranked = self.scorer.rank_goals(posteriors)
            
            # Prepare results
            result = {
                'observations': observations,
                'candidate_goals': candidate_goals,
                'costs': all_costs,
                'posteriors': posteriors,
                'cost_differences': cost_diffs,
                'ranked_goals': ranked,
                'top_goal': ranked[0][0] if ranked else None,
                'top_probability': ranked[0][1] if ranked else 0.0,
            }
            
            self.results_history.append(result)
            
            return result
        
        except Exception as e:
            print(f"\n[ERROR] Recognition failed:")
            traceback.print_exc()
            return {'error': str(e)}
    
    def print_results(self, result: Dict):
        """Pretty-print recognition results."""
        if 'error' in result:
            print(f"\n[ERROR] {result['error']}")
            return
        
        print("\n" + "="*70)
        print("RESULTS")
        print("="*70)
        print(f"Top goal: {result['top_goal']}")
        print(f"Confidence: {result['top_probability']:.4f}")
        print("\nGoal Rankings:")
        for i, (goal, prob) in enumerate(result['ranked_goals'], 1):
            bar = "█" * int(prob * 40)
            print(f"  {i}. {goal:20s} {prob:.6f} {bar}")
        
        print("\nCost Differences:")
        for goal in result['candidate_goals']:
            delta = result['cost_differences'].get(goal, 0.0)
            print(f"  {goal:20s}: Δ(G,O) = {delta:8.1f}")
    
    def save_results(self, result: Dict, output_file: str):
        """Save results to JSON file."""
        # Convert special values
        data = json.loads(json.dumps(result, default=str))
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\nResults saved to: {output_file}")
    
    def check_planner(self) -> bool:
        """Verify planner is available."""
        if self.planner.verify_setup():
            print("[OK] Planner is available")
            return True
        else:
            print("[WARNING] Could not verify planner. Make sure Fast Downward is installed.")
            print("         Install: apt install fast-downward")
            return False
