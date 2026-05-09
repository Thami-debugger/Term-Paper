"""
Bayesian Scoring for Plan Recognition
Implements Equations 2-5 from the paper.
"""

import math
from typing import Dict, List, Tuple
import numpy as np


class BayesianScorer:
    """Computes posterior goal probabilities using Bayesian inference."""
    
    def __init__(self, beta: float = 1.0):
        """
        Args:
            beta: Temperature parameter for Boltzmann distribution.
                  Higher β → sharper probability peaks.
                  Lower β → more uniform distribution.
        """
        self.beta = beta
    
    def compute_likelihood(
        self,
        compliant_cost: float,
        noncompliant_cost: float
    ) -> Tuple[float, float]:
        """
        Computes P(O|G) and P(Ō|G) using Boltzmann distribution.
        
        From Equations 2-3:
        P(O|G) = α' exp{-β c(G, O)}
        P(Ō|G) = α' exp{-β c(G, Ō)}
        
        Returns:
            Tuple of (P(O|G), P(Ō|G)) normalized to sum to 1
        """
        # Handle infinite costs
        if math.isinf(compliant_cost) and math.isinf(noncompliant_cost):
            return 0.5, 0.5
        if math.isinf(compliant_cost):
            return 0.0, 1.0
        if math.isinf(noncompliant_cost):
            return 1.0, 0.0
        
        # Compute unnormalized probabilities
        p_O_given_G = math.exp(-self.beta * compliant_cost)
        p_not_O_given_G = math.exp(-self.beta * noncompliant_cost)
        
        # Normalize
        total = p_O_given_G + p_not_O_given_G
        if total == 0:
            return 0.5, 0.5
        
        return p_O_given_G / total, p_not_O_given_G / total
    
    def compute_cost_difference(
        self,
        compliant_cost: float,
        noncompliant_cost: float
    ) -> float:
        """
        Computes Δ(G, O) = c(G, O) - c(G, Ō).
        
        From Equation 5.
        """
        if math.isinf(compliant_cost) or math.isinf(noncompliant_cost):
            # Handle edge cases
            if math.isinf(compliant_cost) and math.isinf(noncompliant_cost):
                return 0.0
            elif math.isinf(compliant_cost):
                return float('inf')
            else:
                return float('-inf')
        
        return compliant_cost - noncompliant_cost
    
    def score_goals(
        self,
        costs: Dict[str, Dict[str, float]],
        priors: Dict[str, float] = None,
        verbose: bool = True
    ) -> Dict[str, float]:
        """
        Computes posterior P(G|O) for all goals using Bayes' rule.
        
        From Equation 1:
        P(G|O) = α P(O|G) P(G)
        
        Args:
            costs: Dict mapping goal name to {'compliant': cost, 'noncompliant': cost}
            priors: Prior P(G) for each goal. Defaults to uniform.
            verbose: Print scoring details
        
        Returns:
            Dict mapping goal name to posterior probability
        """
        if priors is None:
            # Uniform priors
            priors = {goal: 1.0 / len(costs) for goal in costs}
        
        posteriors = {}
        cost_diffs = {}
        
        if verbose:
            print("\n[Bayesian Scorer] Computing posteriors:")
            print(f"  β = {self.beta}")
        
        # Compute likelihoods and cost differences
        for goal, cost_dict in costs.items():
            compliant_cost = cost_dict['compliant']
            noncompliant_cost = cost_dict['noncompliant']
            
            # Compute likelihood
            p_O, p_not_O = self.compute_likelihood(compliant_cost, noncompliant_cost)
            
            # Compute cost difference
            delta = self.compute_cost_difference(compliant_cost, noncompliant_cost)
            cost_diffs[goal] = delta
            
            # Bayes' rule: P(G|O) ∝ P(O|G) P(G)
            prior = priors.get(goal, 1.0 / len(costs))
            posteriors[goal] = p_O * prior
            
            if verbose:
                print(f"  {goal:20s}: c(G,O)={compliant_cost:8.1f}, "
                      f"c(G,Ō)={noncompliant_cost:8.1f}, Δ={delta:8.1f}, "
                      f"P(O|G)={p_O:.4f}, P(G|O)∝{posteriors[goal]:.6f}")
        
        # Normalize posteriors
        total = sum(posteriors.values())
        if total > 0:
            posteriors = {g: p / total for g, p in posteriors.items()}
        
        if verbose:
            print("\n  Normalized posteriors:")
            sorted_goals = sorted(posteriors.items(), key=lambda x: x[1], reverse=True)
            for goal, prob in sorted_goals:
                print(f"    {goal:20s}: {prob:.6f}")
        
        return posteriors, cost_diffs
    
    def rank_goals(
        self,
        posteriors: Dict[str, float],
        threshold: float = 0.0
    ) -> List[Tuple[str, float]]:
        """
        Returns goals ranked by posterior probability.
        
        Args:
            posteriors: Dict of goal -> posterior probability
            threshold: Only return goals with posterior >= threshold
        
        Returns:
            Sorted list of (goal, probability) tuples
        """
        ranked = sorted(
            posteriors.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        if threshold > 0:
            ranked = [(g, p) for g, p in ranked if p >= threshold]
        
        return ranked
