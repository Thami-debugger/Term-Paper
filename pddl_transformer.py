"""
PDDL Transformer for Plan Recognition
Implements Definition 2 and Proposition 3 from the paper:
Transforms a domain and observation sequence into modified planning problems
for compliant (G + O) and non-compliant (G + Ō) goals.
"""

import re
from pathlib import Path
from typing import List, Tuple, Dict


class PDDLTransformer:
    """Transforms PDDL domain and observation sequence according to the paper."""
    
    def __init__(self, domain_text: str, problem_text: str, observations: List[str]):
        """
        Args:
            domain_text: Original PDDL domain
            problem_text: Original PDDL problem
            observations: List of observed action names
        """
        self.domain_text = domain_text
        self.problem_text = problem_text
        self.observations = observations
        self.observation_fluents = [f"p_{action}" for action in observations]
    
    def transform_domain(self) -> str:
        """
        Transforms domain P to P' by adding observation fluents.
        
        From Definition 2:
        - F' = F ∪ { p_a | a ∈ O }
        - I' = I
        - A' = A (with modified action effects for observed actions)
        """
        domain = self.domain_text
        
        # Extract predicates section
        predicates_match = re.search(r'(:predicates\s*\((.*?)\))', domain, re.DOTALL)
        if not predicates_match:
            raise ValueError("Could not find :predicates section in domain")
        
        predicates_content = predicates_match.group(2)
        
        # Add new observation predicates
        new_predicates = " ".join([f"({fluent})" for fluent in self.observation_fluents])
        updated_predicates = f"(:predicates\n{predicates_content}\n    {new_predicates}\n  )"
        
        domain = domain.replace(predicates_match.group(1), updated_predicates)
        
        # Modify action effects for observed actions
        domain = self._modify_action_effects(domain)
        
        return domain
    
    def _modify_action_effects(self, domain: str) -> str:
        """
        Modifies actions to add observation fluent effects.
        For action a in O:
        - If a is first in O: add effect (p_a)
        - If b precedes a in O: add effect (when (p_b) (p_a))
        """
        for i, action in enumerate(self.observations):
            # Find action definition
            action_pattern = rf'(:action\s+{re.escape(action)}\b(.*?)(?=:action|$))'
            match = re.search(action_pattern, domain, re.DOTALL | re.IGNORECASE)
            
            if match:
                action_def = match.group(1)
                
                # Find :effect section
                effect_match = re.search(r'(:effect\s*\((.*?)\))', action_def, re.DOTALL)
                if effect_match:
                    effect_content = effect_match.group(2)
                    
                    # Build new effect
                    if i == 0:
                        # First action: just add (p_a)
                        new_effect = f"(and {effect_content} ({self.observation_fluents[i]}))"
                    else:
                        # Subsequent action: add (when (p_prev) (p_a))
                        prev_fluent = self.observation_fluents[i - 1]
                        new_effect = f"(and {effect_content} (when ({prev_fluent}) ({self.observation_fluents[i]})))"
                    
                    updated_effect = f"(:effect ({new_effect}))"
                    action_def = action_def.replace(effect_match.group(1), updated_effect)
                    
                    domain = domain.replace(match.group(1), action_def)
        
        return domain
    
    def create_compliant_problem(self, goal_text: str) -> str:
        """
        Creates problem with goal G + O (observation-compliant).
        Goal is: (and <original_goal> (p_last_observation))
        """
        problem = self.problem_text
        
        # Extract current goal
        goal_match = re.search(r'(:goal\s*\((.*?)\))', problem, re.DOTALL)
        if not goal_match:
            raise ValueError("Could not find :goal section in problem")
        
        current_goal = goal_match.group(2).strip()
        
        # Add observation fluent constraint
        last_fluent = self.observation_fluents[-1]
        new_goal = f"(and {current_goal} ({last_fluent}))"
        
        updated_goal = f"(:goal ({new_goal}))"
        problem = problem.replace(goal_match.group(1), updated_goal)
        
        return problem
    
    def create_noncompliant_problem(self, goal_text: str) -> str:
        """
        Creates problem with goal G + Ō (observation non-compliant).
        Goal is: (and <original_goal> (not (p_last_observation)))
        """
        problem = self.problem_text
        
        # Extract current goal
        goal_match = re.search(r'(:goal\s*\((.*?)\))', problem, re.DOTALL)
        if not goal_match:
            raise ValueError("Could not find :goal section in problem")
        
        current_goal = goal_match.group(2).strip()
        
        # Add negated observation fluent constraint
        last_fluent = self.observation_fluents[-1]
        new_goal = f"(and {current_goal} (not ({last_fluent})))"
        
        updated_goal = f"(:goal ({new_goal}))"
        problem = problem.replace(goal_match.group(1), updated_goal)
        
        return problem
    
    def save_transformed_files(self, output_dir: Path, basename: str = "transformed"):
        """Saves transformed domain and both problem variants."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        transformed_domain = self.transform_domain()
        compliant_problem = self.create_compliant_problem(self.problem_text)
        noncompliant_problem = self.create_noncompliant_problem(self.problem_text)
        
        (output_dir / f"{basename}_domain.pddl").write_text(transformed_domain)
        (output_dir / f"{basename}_problem_compliant.pddl").write_text(compliant_problem)
        (output_dir / f"{basename}_problem_noncompliant.pddl").write_text(noncompliant_problem)
        
        return {
            "domain": str(output_dir / f"{basename}_domain.pddl"),
            "compliant": str(output_dir / f"{basename}_problem_compliant.pddl"),
            "noncompliant": str(output_dir / f"{basename}_problem_noncompliant.pddl"),
        }
