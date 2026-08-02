import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from predictor_ops.health import HealthPolicy, assess, load_heartbeat
from predictor_ops.models import OperationalState
from predictor_ops.windows import TaskQuery

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def _policy(tmp_path):
    return HealthPolicy(job_id="job", heartbeat_path=tmp_path / "heartbeat.json", max_age_seconds=60)


def _write(policy, status="SUCCEEDED", finished=None):
    policy.heartbeat_path.write_text(json.dumps({"status": status, "finished_at": finished or NOW.isoformat()}))


def test_recent_success_is_healthy_and_deterministic(tmp_path):
    policy = _policy(tmp_path)
    _write(policy)
    first = assess(policy, TaskQuery(OperationalState.SUCCEEDED, {}), now=NOW)
    second = assess(policy, TaskQuery(OperationalState.SUCCEEDED, {}), now=NOW)
    assert first == second and first["status"] is OperationalState.SUCCEEDED


def test_scheduler_failure_wins_and_expected_disabled_is_skipped(tmp_path):
    policy = _policy(tmp_path)
    _write(policy)
    failed = assess(policy, TaskQuery(OperationalState.FAILED, {}, "last result"), now=NOW)
    assert failed["status"] is OperationalState.FAILED
    policy.expected_enabled = False
    skipped = assess(policy, TaskQuery(OperationalState.SKIPPED, {}, "disabled"), now=NOW)
    assert skipped["status"] is OperationalState.SKIPPED


@pytest.mark.parametrize("status", ["SOURCE_UNAVAILABLE", "PARTIAL", "DEGRADED", "FAILED"])
def test_absence_and_degraded_states_are_never_success(tmp_path, status):
    policy = _policy(tmp_path)
    _write(policy, status=status)
    assert assess(policy, None, now=NOW)["status"] is not OperationalState.SUCCEEDED


def test_missing_invalid_and_stale_heartbeat_fail_closed(tmp_path):
    policy = _policy(tmp_path)
    assert assess(policy, None, now=NOW)["status"] is OperationalState.FAILED
    policy.heartbeat_path.write_text("bad-json")
    assert load_heartbeat(policy.heartbeat_path) is None
    _write(policy, finished=(NOW - timedelta(seconds=61)).isoformat())
    assert assess(policy, None, now=NOW)["reason"] == "heartbeat stale"
    _write(policy, finished="invalid")
    assert assess(policy, None, now=NOW)["reason"] == "heartbeat time invalid"


def test_health_policy_rejects_unknown_fields(tmp_path):
    with pytest.raises(ValidationError):
        HealthPolicy.model_validate(
            {"job_id": "x", "heartbeat_path": tmp_path / "x", "max_age_seconds": 1, "unknown": True}
        )
