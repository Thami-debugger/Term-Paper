"""
Planner Integration Module
Handles execution of classical planners (Fast Downward) and cost extraction.
"""

import subprocess
import tempfile
import re
from pathlib import Path
from typing import Optional, Dict, Tuple
import json


class PlannerInterface:
    """Interface to classical planners like Fast Downward."""
    
    def __init__(self, planner_path: str = "fd"):
        """
        Args:
            planner_path: Path to planner executable or command name
        """
        self.planner_path = planner_path
    
    def solve(
        self, 
        domain_file: str, 
        problem_file: str, 
        timeout: int = 60,
        verbose: bool = True
    ) -> Dict[str, any]:
        """
        Solves a planning problem using Fast Downward.
        
        Returns:
            Dict with keys:
            - 'cost': Plan cost (int), or float('inf') if unsolvable
            - 'plan': Plan as list of actions, or empty list if unsolvable
            - 'success': Boolean indicating success
            - 'stderr': Error/output messages
        """
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                output_file = f.name
            
            # Build Fast Downward command
            cmd = [
                self.planner_path,
                domain_file,
                problem_file,
                "--search", "astar(lmcut())",
                "--plan-file", output_file,
            ]
            
            if verbose:
                print(f"[Planner] Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if verbose:
                print(f"[Planner] Return code: {result.returncode}")
            
            # Parse output to extract cost
            cost = self._extract_cost(result.stderr)
            plan = self._extract_plan(output_file) if Path(output_file).exists() else []
            
            # Cleanup temp file
            try:
                Path(output_file).unlink()
            except:
                pass
            
            return {
                'cost': cost,
                'plan': plan,
                'success': result.returncode == 0,
                'stderr': result.stderr,
                'stdout': result.stdout,
            }
        
        except subprocess.TimeoutExpired:
            return {
                'cost': float('inf'),
                'plan': [],
                'success': False,
                'stderr': f'Timeout after {timeout}s',
                'stdout': '',
            }
        except Exception as e:
            return {
                'cost': float('inf'),
                'plan': [],
                'success': False,
                'stderr': str(e),
                'stdout': '',
            }
    
    def _extract_cost(self, stderr_output: str) -> float:
        """Extracts plan cost from Fast Downward stderr output."""
        # Look for "Plan cost: X" pattern
        match = re.search(r'Plan cost:\s*([\d.]+)', stderr_output)
        if match:
            try:
                return float(match.group(1))
            except:
                return float('inf')
        
        # If no cost found and error mentions unsolvable, return inf
        if 'unsolvable' in stderr_output.lower():
            return float('inf')
        
        return float('inf')
    
    def _extract_plan(self, plan_file: str) -> list:
        """Extracts plan from Fast Downward output file."""
        try:
            with open(plan_file, 'r') as f:
                lines = f.readlines()
            
            plan = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith(';'):
                    # Extract action name
                    action_match = re.search(r'\((.*?)\)', line)
                    if action_match:
                        plan.append(action_match.group(1))
            
            return plan
        except:
            return []
    
    def verify_setup(self) -> bool:
        """Check if planner is available."""
        try:
            result = subprocess.run(
                [self.planner_path, "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False


class CostComputer:
    """Computes costs for goal recognition."""
    
    def __init__(self, planner: PlannerInterface):
        self.planner = planner
    
    def compute_costs(
        self,
        domain_file: str,
        compliant_problem: str,
        noncompliant_problem: str,
        goal_name: str,
        verbose: bool = True
    ) -> Dict[str, float]:
        """
        Computes c(G, O) and c(G, Ō) for a goal.
        
        Returns:
            Dict with keys 'compliant' and 'noncompliant' containing costs
        """
        if verbose:
            print(f"\n[CostComputer] Computing costs for goal: {goal_name}")
        
        # Solve compliant problem
        if verbose:
            print(f"  → Solving compliant problem (G + O)...")
        compliant_result = self.planner.solve(
            domain_file, compliant_problem, verbose=verbose
        )
        compliant_cost = compliant_result['cost']
        
        if verbose:
            print(f"    Cost: {compliant_cost}")
        
        # Solve non-compliant problem
        if verbose:
            print(f"  → Solving non-compliant problem (G + Ō)...")
        noncompliant_result = self.planner.solve(
            domain_file, noncompliant_problem, verbose=verbose
        )
        noncompliant_cost = noncompliant_result['cost']
        
        if verbose:
            print(f"    Cost: {noncompliant_cost}")
        
        return {
            'compliant': compliant_cost,
            'noncompliant': noncompliant_cost,
            'compliant_plan': compliant_result['plan'],
            'noncompliant_plan': noncompliant_result['plan'],
        }
