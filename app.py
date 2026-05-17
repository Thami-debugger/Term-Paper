import streamlit as st
import os
import sys
import json
import pandas as pd
from pathlib import Path
import statistics
import shutil
import traceback
from typing import Any, Callable

# Ensure src/ is importable
ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from evaluate import run_instance
except ImportError:
    run_instance = None
    st.error("Could not find 'src/evaluate.py'. Ensure this script sits in your repository root.")

backend_run_instance: Callable[..., dict[str, Any] | None] | None = run_instance

# Page Configuration
st.set_page_config(page_title="Probabilistic Plan Recognition UI", layout="wide", page_icon="🤖")

st.title("🤖 Probabilistic Plan Recognition Explorer")
st.caption("Interactive verification engine for the Ramírez & Geffner (AAAI-10) architecture.")
st.markdown("---")

# Sidebar Configuration Layout
st.sidebar.header("🔧 Experimental Framework Tuning")
selected_domain = st.sidebar.selectbox(
    "Select Target Planning Domain",
    ["blocks-world", "easy-ipc-grid", "logistics", "intrusion-detection", "campus", "kitchen"]
)

selected_planner = st.sidebar.selectbox(
    "Select Configuration Profile",
    ["HSP", "LAMA", "GREEDY_LAMA"]
)

obs_level = st.sidebar.slider("Observation Chaining Density (%)", 10, 100, 50, step=10)
beta = st.sidebar.number_input("Boltzmann Scaling Modifier (β)", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
timeout = st.sidebar.number_input("Max Solver Boundary Cutoff (s)", min_value=10, max_value=1800, value=300, step=10)

# Main Grid Layout
col_controls, col_display = st.columns([1, 2])

with col_controls:
    st.subheader("📁 Instance Loader")
    target_archive_path = None
    
    # Dynamic path mapping to check local data folders
    benchmarks_base = ROOT / "benchmarks" / "experiments" / selected_domain / str(obs_level)
    
    if benchmarks_base.is_dir():
        archives = sorted(list(benchmarks_base.glob("*.tar.bz2")))
        archive_names = [a.name for a in archives]
        
        if archive_names:
            selected_archive_name = st.selectbox("Select Benchmark Archive Instance", archive_names)
            target_archive_path = benchmarks_base / selected_archive_name
            st.success(f"Loaded instance structural reference successfully: {selected_archive_name}")
            
            run_trigger = st.button("🚀 Fire Subprocess Pipeline Engine", type="primary", use_container_width=True)
        else:
            st.warning(f"No compressed experimental archives (*.tar.bz2) detected inside path: {benchmarks_base}")
            run_trigger = False
    else:
        st.error(f"Target directory path not detected: {benchmarks_base}")
        run_trigger = False

with col_display:
    st.subheader("🖥️ Live Pipeline Stdout Console Monitoring")
    
    if run_trigger and target_archive_path:
        log_placeholder = st.empty()
        log_placeholder.info("Initializing PDDL compilation matrix & triggering background solver threads...")

        if backend_run_instance is None:
            log_placeholder.error("Pipeline Failure: backend evaluator is unavailable (src/evaluate.py import failed).")
            st.stop()
        assert backend_run_instance is not None

        # Preflight compatibility checks for common platform/planner failures.
        preflight_issues = []
        if selected_domain == "kitchen" and selected_planner == "HSP":
            preflight_issues.append(
                "Kitchen + HSP is unsupported in this setup because the domain uses conditional effects, "
                "while this HSP configuration does not support them."
            )

        if sys.platform == "win32" and not os.environ.get("FAST_DOWNWARD") and shutil.which("wsl") is None:
            preflight_issues.append(
                "Windows host detected without WSL and no FAST_DOWNWARD path set; planner subprocess cannot start."
            )

        if preflight_issues:
            log_placeholder.error(
                "Pipeline blocked by compatibility checks:\n- " + "\n- ".join(preflight_issues)
            )
            st.info("Try switching planner/domain (e.g., LAMA for kitchen) or configure planner runtime first.")
            st.stop()
        
        # Capture metrics
        import time
        start_wall = time.perf_counter()
        
        # Execute the core component via the backend
        with st.spinner("Processing optimization parameters inside isolated native thread..."):
            try:
                result = backend_run_instance(
                    str(target_archive_path),
                    beta=beta,
                    timeout=timeout,
                    planner_profile=selected_planner,
                    verbose=False
                )
            except Exception as exc:
                result = None
                log_placeholder.error(
                    "Pipeline Failure: execution raised an exception.\n"
                    f"Type: {type(exc).__name__}\n"
                    f"Details: {exc}"
                )
                st.code("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), language="text")
        
        elapsed_wall = time.perf_counter() - start_wall
        
        if result is None:
            log_placeholder.error(
                "Pipeline Failure: evaluation returned no result.\n"
                "Common causes:\n"
                "- Planner/domain incompatibility (for example, kitchen + HSP).\n"
                "- Fast Downward subprocess failure or timeout.\n"
                "- Platform runtime mismatch (Windows/WSL planner bridge)."
            )
        else:
            log_placeholder.empty()
            st.toast("Evaluation tracking matrix updated successfully!", icon="✅")
            
            # Display primary summary metrics inside presentation cards
            st.markdown("### 📊 Calculated Metrics Summary")
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            
            planner_time = result.get("runtime", result.get("time", elapsed_wall))
            
            metric_col1.metric("Tracking Precision (Q)", f"{result['Q']:.3f}")
            metric_col2.metric("Active Goal Space (S)", f"{result['S']:.3f}")
            metric_col3.metric("Solver Process Time (T)", f"{planner_time:.2f}s")
            
            # Display detailed tabular raw data array breakdown
            st.markdown("### 📋 Full Evaluation Metadata Record")
            flat_data = {
                "Metadata Field Parameter": [
                    "Target Evaluation Domain", "Action Track Density", "Planner Engine Branch", 
                    "Applied Boltzmann Scaling (β)", "Internal Planner Computational Time", "Pipeline Wall Clock Time"
                ],
                "Calculated Output Value": [
                    selected_domain, f"{obs_level}%", selected_planner, 
                    str(beta), f"{planner_time:.4f} seconds", f"{elapsed_wall:.4f} seconds"
                ]
            }
            st.table(pd.DataFrame(flat_data))
    else:
        st.info("System idle. Adjust sidebar parameter thresholds and click the trigger execution button to begin tracking analysis.")