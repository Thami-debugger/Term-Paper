# Term-Paper

This repository contains the code and data for the COMS7044A reproducibility assignment on probabilistic plan recognition.

## Project Structure
- `app.py` - Interactive Streamlit demo for single-instance plan recognition evaluation.
- `observable_runner.py` - Main runner for reproduction experiments (batch mode).
- `src/` - Core pipeline modules (`compiler.py`, `solver.py`, `scoring.py`, `evaluate.py`).
- `benchmarks/experiments/` - Benchmark archives used in evaluation.
- `results/` - Output CSV and JSON files from batch runs.
- `report/` - Report artifacts.

## Requirements
- Windows PowerShell or Linux shell.
- Python 3.13 (recommended) with dependencies installed in `.venv`.
- Fast Downward available to the solver environment.

### Dependency Summary
- Python packages are installed from `requirements.txt`.
- External planner dependency: Fast Downward (not a pip package).

## How To Run

### Environment Setup (Required for Both Demo and Reproduction)

#### 1) Activate environment (PowerShell)
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".venv\Scripts\Activate.ps1"
```

#### 2) Install dependencies (if not already installed)
```powershell
pip install -r requirements.txt
```

#### 3) Ensure Fast Downward is available

The solver calls Fast Downward as an external program. You must either:
- install `fast-downward` / `fast-downward.py` so it is on PATH, or
- set the `FAST_DOWNWARD` environment variable to the full path of `fast-downward.py`.

PowerShell example:
```powershell
$env:FAST_DOWNWARD = "C:\downward\fast-downward.py"
```

Quick check (PowerShell):
```powershell
python -c "from src.solver import get_fd_command; print('Fast Downward command:', get_fd_command())"
```

---

### Interactive Demo (Graphical User Interface)

The Streamlit web interface allows you to test the plan recognition pipeline interactively on individual benchmark instances.

#### Launch the demo:
```powershell
streamlit run app.py
```

This opens a browser window at `http://localhost:8501` with an interactive dashboard where you can:
- Select a planning domain (blocks-world, campus, kitchen, etc.)
- Choose a planner configuration (HSP, LAMA, Greedy LAMA)
- Adjust observation density (10%–100%)
- Tune Boltzmann scaling parameter (β)
- Select a benchmark instance to evaluate
- View live metrics: tracking precision (Q), active goal space (S), and solver time (T)

**Demo Features:**
- Real-time instance loading from `benchmarks/experiments/`
- Live stdout monitoring during evaluation
- Preflight compatibility checks (domain/planner combos)
- Detailed metadata and metric tables

---

### Batch Reproducibility (Command-Line Reproduction)

For systematic reproduction of paper results across multiple domains and planners.

#### Run full reproduction (all planners, all domains):
```powershell
python observable_runner.py --compare-paper
```

#### Quick smoke test (2 instances per level):
```powershell
python observable_runner.py --max-instances 2 --compare-paper
```

#### Example: Single domain with specific planner
```powershell
python observable_runner.py --domains campus --obs-levels 10 --planners HSP --max-instances 1 --compare-paper
```

---

## Batch Options & Parameters
- `--domains blocks-world easy-ipc-grid logistics intrusion-detection campus kitchen`
- `--obs-levels 10 30 50 70 100`
- `--planners HSP LAMA GREEDY_LAMA`
- `--max-instances N` (limit archives per observation level)
- `--timeout 300` (per solver call)
- `--beta 1.0`
- `--compare-paper`
- `--paper-targets <path-to-json>`

## Outputs

### Interactive Demo Output
- Live metric display: Tracking Precision (Q), Active Goal Space (S), Solver Time (T)
- No persistent output files (single instance evaluation)

### Batch Run Output
- Per-domain CSV files in `results/` (e.g., `blocks-world_hsp_observable_results.csv`)
- Per-domain JSON files with detailed instance-level data
- Combined results file: `results/observable_all_results.json`
- Console summary table with mean and standard deviation for Q and S metrics
- Optional paper comparison delta output (with `--compare-paper`)

## Reproducibility Notes

- **Paper Baselines:** The runner includes baseline targets from Ramírez & Geffner (AAAI-10) for blocks-world and easy-ipc-grid at 50% observation level. Use `--compare-paper` to see deltas.
- **Planner Compatibility:** HSP does not support domains with conditional effects (e.g., kitchen). Use LAMA or Greedy LAMA for these domains.
- **Performance:** Full runs across all domains and observation levels may take several hours. Use `--max-instances` to limit instances per level for faster testing.
- **Environment:** Fast Downward must be available on your PATH or set via `FAST_DOWNWARD` environment variable.
- **Windows:** Prefer running commands inside the activated `.venv` in PowerShell.
