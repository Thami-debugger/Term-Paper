# Term-Paper

This repository contains the code and data for the COMS7044A reproducibility assignment on probabilistic plan recognition.

## Project Structure
- `observable_runner.py` - Main runner for reproduction experiments.
- `src/` - Core pipeline modules (`compiler.py`, `solver.py`, `scoring.py`, `evaluate.py`).
- `benchmarks/experiments/` - Benchmark archives used in evaluation.
- `results/` - Output CSV and JSON files.
- `report/` - Report artifacts.

## Requirements
- Windows PowerShell or Linux shell.
- Python 3.13 (recommended) with dependencies installed in `.venv`.
- Fast Downward available to the solver environment.

## How To Run

### 1) Activate environment (PowerShell)
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".venv\Scripts\Activate.ps1"
```

### 2) Run the main reproduction command
```powershell
python observable_runner.py --compare-paper
```

If `python3` is not available in PowerShell, use `python` as above.

### 3) Quick smoke test (small run)
```powershell
python observable_runner.py --max-instances 2 --compare-paper
```

### 4) Example targeted run (single domain)
```powershell
python observable_runner.py --domains campus --obs-levels 10 --planners HSP --max-instances 1 --compare-paper
```

## Useful Options
- `--domains blocks-world easy-ipc-grid logistics intrusion-detection campus kitchen`
- `--obs-levels 10 30 50 70 100`
- `--planners HSP LAMA GREEDY_LAMA`
- `--max-instances N` (limit archives per observation level)
- `--timeout 300` (per solver call)
- `--beta 1.0`
- `--compare-paper`
- `--paper-targets <path-to-json>`

## Outputs
- Per-domain planner CSVs in `results/`.
- Combined JSON file: `results/observable_all_results.json`.
- Console summary table with mean and standard deviation for Q and S.

## Notes
- Long full runs may take substantial time.
- On Windows, prefer running inside the activated `.venv` and use `python` commands.
