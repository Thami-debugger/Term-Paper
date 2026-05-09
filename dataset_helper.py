"""
Dataset Utility - Extract and prepare data from tar archives.
Helps extract PDDL files and observation sequences from the dataset.
"""

import tarfile
import json
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import re


class DatasetHelper:
    """Utilities for working with the goal-plan-recognition-dataset."""
    
    @staticmethod
    def extract_archive(tar_path: str, extract_to: Optional[str] = None) -> Dict[str, Path]:
        """
        Extracts a tar.bz2 archive from the dataset.
        
        Args:
            tar_path: Path to .tar.bz2 file
            extract_to: Directory to extract to (default: temp dir)
        
        Returns:
            Dict with keys: 'domain', 'problem', 'extract_dir'
        """
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
                files['domain'] = file
            elif 'problem' in file.name.lower():
                files['problem'] = file
        
        files['extract_dir'] = extract_path
        return files
    
    @staticmethod
    def find_archives(dataset_root: str, domain: str, observation_level: int = 50) -> List[str]:
        """
        Finds all archives for a domain at a given observation level.
        
        Args:
            dataset_root: Root of goal-plan-recognition-dataset
            domain: Domain name (e.g., 'blocks-world', 'campus')
            observation_level: Observation percentage (10, 30, 50, 70, 100)
        
        Returns:
            List of paths to .tar.bz2 files
        """
        domain_path = Path(dataset_root) / domain / str(observation_level)
        
        if not domain_path.exists():
            return []
        
        return sorted([str(f) for f in domain_path.glob("*.tar.bz2")])
    
    @staticmethod
    def parse_archive_name(filename: str) -> Dict[str, str]:
        """
        Parses archive filename to extract metadata.
        
        Examples:
        - blocks-world_p01_hyp-0_10_0.tar.bz2
        - campus_p02_hyp-3_50_1.tar.bz2
        
        Returns:
            Dict with keys: domain, problem_id, hypothesis_id, obs_level, seed
        """
        # Remove .tar.bz2 extension
        name = filename.replace('.tar.bz2', '')
        
        # Pattern: domain_pXX_hyp-Y_ZZ_S
        pattern = r'(.+?)_p(\d+)_hyp-(\d+)_(\d+)_(\d+)'
        match = re.match(pattern, name)
        
        if match:
            return {
                'domain': match.group(1),
                'problem_id': match.group(2),
                'hypothesis_id': match.group(3),
                'obs_level': int(match.group(4)),
                'seed': match.group(5),
            }
        
        return {}
    
    @staticmethod
    def extract_observation_sequence(obs_file: Path) -> List[str]:
        """
        Extracts observation sequence from file.
        
        Assumes one action per line or JSON format.
        """
        if not obs_file.exists():
            return []
        
        content = obs_file.read_text().strip()
        
        # Try JSON format
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
        except:
            pass
        
        # Try line-by-line format
        lines = content.split('\n')
        actions = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # Extract action name (handle PDDL format)
                if '(' in line:
                    action = line.split('(')[1].split(')')[0].strip()
                    actions.append(action)
                else:
                    actions.append(line)
        
        return actions
    
    @staticmethod
    def get_goals_from_problem(problem_pddl: str) -> List[str]:
        """
        Extracts goal names from PDDL problem file.
        
        Returns list of goal fluents.
        """
        # Extract :goal section
        goal_match = re.search(r':goal\s*\((.*?)\)', problem_pddl, re.DOTALL)
        if not goal_match:
            return []
        
        goal_content = goal_match.group(1)
        
        # Extract all predicates in the goal
        predicates = re.findall(r'\((\w+(?:\s+\w+)*)\)', goal_content)
        return list(set(predicates))
    
    @staticmethod
    def batch_extract(
        dataset_root: str,
        domain: str,
        observation_levels: List[int] = None,
        max_archives: int = 3
    ) -> Dict[int, List[Dict]]:
        """
        Batch extract archives for a domain at multiple observation levels.
        
        Args:
            dataset_root: Root of dataset
            domain: Domain name
            observation_levels: Which levels to extract (default: [10, 50, 100])
            max_archives: Max archives per level
        
        Returns:
            Dict mapping observation_level -> list of extracted data
        """
        if observation_levels is None:
            observation_levels = [10, 50, 100]
        
        results = {}
        
        for level in observation_levels:
            print(f"\nExtracting {domain} at {level}% observation...")
            
            archives = DatasetHelper.find_archives(dataset_root, domain, level)
            print(f"  Found {len(archives)} archives, extracting first {max_archives}...")
            
            level_data = []
            for archive_path in archives[:max_archives]:
                try:
                    print(f"    Extracting {Path(archive_path).name}...")
                    extracted = DatasetHelper.extract_archive(archive_path)
                    
                    metadata = DatasetHelper.parse_archive_name(Path(archive_path).name)
                    metadata['domain_file'] = str(extracted['domain'])
                    metadata['problem_file'] = str(extracted['problem'])
                    metadata['extract_dir'] = str(extracted['extract_dir'])
                    
                    level_data.append(metadata)
                    print(f"      ✓ Extracted")
                
                except Exception as e:
                    print(f"      ✗ Error: {e}")
            
            results[level] = level_data
        
        return results
    
    @staticmethod
    def print_dataset_summary(dataset_root: str):
        """Print summary of dataset structure."""
        print("\nDataset Summary:")
        print("="*70)
        
        root = Path(dataset_root)
        domains = sorted([d for d in root.iterdir() if d.is_dir() and not d.name.startswith('.')])
        
        for domain_dir in domains:
            if domain_dir.name.endswith('-noisy'):
                continue
            
            print(f"\n{domain_dir.name}:")
            
            obs_levels = sorted([d.name for d in domain_dir.iterdir() if d.is_dir()])
            for level in obs_levels:
                archives = list((domain_dir / level).glob("*.tar.bz2"))
                print(f"  {level}%: {len(archives)} archives")
