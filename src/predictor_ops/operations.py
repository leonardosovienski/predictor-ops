from __future__ import annotations

import hashlib
from enum import StrEnum

from .models import JobConfig, JobType, RiskSnapshot


class OrderState(StrEnum):
    PRE_SUBMISSION_FAILURE = "PRE_SUBMISSION_FAILURE"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    API_TIMEOUT = "API_TIMEOUT"


class RetryAction(StrEnum):
    RETRY_SAFE = "RETRY_SAFE"
    QUERY_EXTERNAL_STATE = "QUERY_EXTERNAL_STATE"
    DO_NOT_RETRY = "DO_NOT_RETRY"
    CONTINUE_RECONCILIATION = "CONTINUE_RECONCILIATION"


def retry_action(state: OrderState) -> RetryAction:
    if state is OrderState.PRE_SUBMISSION_FAILURE:
        return RetryAction.RETRY_SAFE
    if state in {OrderState.SUBMISSION_UNKNOWN, OrderState.API_TIMEOUT}:
        return RetryAction.QUERY_EXTERNAL_STATE
    if state is OrderState.PARTIALLY_FILLED:
        return RetryAction.CONTINUE_RECONCILIATION
    return RetryAction.DO_NOT_RETRY


def economic_lock_id(job: JobConfig) -> str:
    if job.economic_key is None:
        return job.id
    digest = hashlib.sha256(job.economic_key.canonical().encode()).hexdigest()
    return f"economic-{digest}"


def kill_switch_reasons(job: JobConfig) -> list[str]:
    """Return deterministic fail-closed reasons before opening a new position."""
    if job.job_type is not JobType.EXECUTION:
        return []
    snapshot: RiskSnapshot | None = job.risk_snapshot
    if snapshot is None:
        return ["risk_snapshot_missing"]
    limits = job.kill_switch_limits
    reasons: list[str] = []
    comparisons = (
        (limits.max_daily_loss, snapshot.daily_loss, "daily_loss_limit"),
        (limits.max_drawdown, snapshot.drawdown, "drawdown_limit"),
        (limits.max_balance_difference, abs(snapshot.balance_difference), "balance_difference_limit"),
        (limits.max_latency_ms, snapshot.latency_ms, "latency_limit"),
        (limits.max_correlated_exposure, snapshot.correlated_exposure, "correlated_exposure_limit"),
    )
    reasons.extend(reason for limit, value, reason in comparisons if limit is not None and value >= limit)
    flags = (
        (snapshot.settlement_healthy, "settlement_unhealthy"),
        (snapshot.odds_source_healthy, "odds_source_degraded"),
        (snapshot.model_recognized, "model_unrecognized"),
        (snapshot.dataset_recognized, "dataset_unrecognized"),
        (not snapshot.drift_detected, "drift_detected"),
    )
    reasons.extend(reason for healthy, reason in flags if not healthy)
    return reasons
