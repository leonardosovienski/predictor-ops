"""Portable operational primitives for predictor workloads."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("predictor-ops")
except PackageNotFoundError:  # source tree without an editable install
    __version__ = "0+unknown"

from .models import EconomicJobKey, JobConfig, JobType, RunStatus
from .operations import OrderState, RetryAction, retry_action
from .runner import RunResult, run_job

__all__ = [
    "EconomicJobKey",
    "JobConfig",
    "JobType",
    "OrderState",
    "RetryAction",
    "RunResult",
    "RunStatus",
    "__version__",
    "retry_action",
    "run_job",
]
