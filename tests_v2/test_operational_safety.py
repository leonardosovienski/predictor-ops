import json
import sys
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from predictor_ops.audit import AppendOnlyAuditLog, CycleStage
from predictor_ops.models import (
    EconomicJobKey,
    JobConfig,
    JobsFile,
    JobType,
    KillSwitchLimits,
    RiskSnapshot,
    RunStatus,
    RuntimeConfig,
)
from predictor_ops.operations import OrderState, RetryAction, retry_action
from predictor_ops.runner import run_job


def key(stage="execute"):
    return EconomicJobKey(
        domain="sports",
        event_id="match-42",
        market="winner",
        decision_stage=stage,
        logical_time=datetime(2026, 8, 17, tzinfo=UTC),
    )


def execution(tmp_path, code="print('sent')", **values):
    return JobConfig(
        id=values.pop("id", "execute"),
        command=[sys.executable, "-c", code],
        job_type=JobType.EXECUTION,
        economic_key=key(),
        capital_permission=True,
        risk_snapshot=values.pop("risk_snapshot", RiskSnapshot()),
        runtime=RuntimeConfig(root=tmp_path),
        **values,
    )


def test_schema_v2_requires_typed_economic_jobs_and_unique_keys():
    with pytest.raises(ValidationError, match="requires job_type and economic_key"):
        JobsFile(schema_version="2", jobs=[JobConfig(id="legacy", command=["echo"])])
    first = JobConfig(id="a", command=["echo"], job_type=JobType.MARKET_COLLECTION, economic_key=key())
    second = JobConfig(id="b", command=["echo"], job_type=JobType.MARKET_COLLECTION, economic_key=key())
    with pytest.raises(ValidationError, match="economic job keys"):
        JobsFile(schema_version="2", jobs=[first, second])


def test_only_execution_jobs_can_receive_capital_permission():
    with pytest.raises(ValidationError, match="allowed only"):
        JobConfig(id="collector", command=["echo"], job_type=JobType.SPORTS_COLLECTION, capital_permission=True)


def test_execution_is_economically_idempotent(tmp_path):
    first = run_job(execution(tmp_path))
    second = run_job(execution(tmp_path, id="retry"))
    assert first.run_status is RunStatus.SUCCEEDED
    assert second.run_status is RunStatus.SKIPPED
    assert second.record["reason"] == "economic_operation_already_claimed"


def test_ambiguous_execution_failure_requires_reconciliation(tmp_path):
    first = run_job(execution(tmp_path, "raise SystemExit(9)"))
    second = run_job(execution(tmp_path, id="unsafe-retry"))
    assert first.run_status is RunStatus.FAILED
    assert second.run_status is RunStatus.SKIPPED
    assert second.record["previous_attempt"]["requires_reconciliation"] is True


def test_retry_policy_never_resubmits_unknown_orders():
    assert retry_action(OrderState.PRE_SUBMISSION_FAILURE) is RetryAction.RETRY_SAFE
    assert retry_action(OrderState.API_TIMEOUT) is RetryAction.QUERY_EXTERNAL_STATE
    assert retry_action(OrderState.SUBMISSION_UNKNOWN) is RetryAction.QUERY_EXTERNAL_STATE
    assert retry_action(OrderState.PARTIALLY_FILLED) is RetryAction.CONTINUE_RECONCILIATION
    assert retry_action(OrderState.ACCEPTED) is RetryAction.DO_NOT_RETRY


def test_kill_switch_fails_closed_and_reports_all_reasons(tmp_path):
    job = execution(
        tmp_path,
        risk_snapshot=RiskSnapshot(
            daily_loss=100,
            settlement_healthy=False,
            odds_source_healthy=False,
            drift_detected=True,
        ),
        kill_switch_limits=KillSwitchLimits(max_daily_loss=100),
    )
    result = run_job(job)
    assert result.run_status is RunStatus.SKIPPED
    assert result.record["reason"] == "kill_switch_open"
    assert set(result.record["kill_switch_reasons"]) >= {
        "daily_loss_limit",
        "settlement_unhealthy",
        "odds_source_degraded",
        "drift_detected",
    }


def test_hash_chained_audit_log_detects_tampering(tmp_path):
    path = tmp_path / "cycle.jsonl"
    audit = AppendOnlyAuditLog(path)
    first = audit.append(CycleStage.SNAPSHOT, {"price": 2.1}, event_id="e1", cycle_id="c1")
    second = audit.append(CycleStage.FORECAST, {"p": 0.55}, event_id="e2", cycle_id="c1")
    assert second["previous_hash"] == first["hash"]
    assert audit.verify() == second["hash"]
    lines = path.read_text().splitlines()
    damaged = json.loads(lines[0])
    damaged["payload"]["price"] = 9
    lines[0] = json.dumps(damaged)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="broken audit chain"):
        audit.verify()


def test_audit_log_enforces_cycle_order_and_allows_multiple_fills(tmp_path):
    audit = AppendOnlyAuditLog(tmp_path / "cycle.jsonl")
    with pytest.raises(ValueError, match="invalid cycle transition"):
        audit.append(CycleStage.ORDER, {}, event_id="e0", cycle_id="c1")
    stages = [
        CycleStage.SNAPSHOT,
        CycleStage.FORECAST,
        CycleStage.DECISION,
        CycleStage.ORDER,
        CycleStage.FILL,
        CycleStage.FILL,
        CycleStage.SETTLEMENT,
    ]
    for index, stage in enumerate(stages):
        audit.append(stage, {}, event_id=f"e{index}", cycle_id="c1")
    with pytest.raises(ValueError, match="invalid cycle transition"):
        audit.append(CycleStage.FILL, {}, event_id="late", cycle_id="c1")
