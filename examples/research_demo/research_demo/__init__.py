"""Minimal research package: seeded synthetic data and summary statistics.

Pure standard library so the workflow can be verified without network installs.
Real projects would typically use NumPy/pandas; the conventions (explicit seeds,
explicit NaN policy, no input mutation, tolerances in tests) carry over.
"""
from .stats import summarize
from .synthetic import make_measurements

__all__ = ["make_measurements", "summarize"]
__version__ = "0.1.0"
