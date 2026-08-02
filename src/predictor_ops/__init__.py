"""Portable operational primitives for predictor workloads."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("predictor-ops")
except PackageNotFoundError:  # source tree without an editable install
    __version__ = "0+unknown"

from .models import JobConfig, OperationalState
from .runner import RunResult, run_job

__all__ = ["JobConfig", "OperationalState", "RunResult", "__version__", "run_job"]
