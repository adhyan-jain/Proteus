"""Central hardware configuration for Proteus pipeline.

Controls thread allocation and GPU resource management across all evaluation
and training scripts to prevent system thrashing and 100% CPU lockups.
"""
import os

# Limit CPU threads for OpenMP / BLAS / MKL to prevent thread explosion across 16 cores
DEFAULT_N_JOBS = min(4, os.cpu_count() or 4)

def configure_environment():
    """Sets system-level environment variables to cap CPU thread usage."""
    os.environ["OMP_NUM_THREADS"] = str(DEFAULT_N_JOBS)
    os.environ["OPENBLAS_NUM_THREADS"] = str(DEFAULT_N_JOBS)
    os.environ["MKL_NUM_THREADS"] = str(DEFAULT_N_JOBS)
    os.environ["VECLIB_MAXIMUM_THREADS"] = str(DEFAULT_N_JOBS)
    os.environ["NUMEXPR_NUM_THREADS"] = str(DEFAULT_N_JOBS)

configure_environment()
