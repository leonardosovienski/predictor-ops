from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RunStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    WAITING = "WAITING"


class JobType(StrEnum):
    SPORTS_COLLECTION = "SPORTS_COLLECTION"
    MARKET_COLLECTION = "MARKET_COLLECTION"
    FORECAST_GENERATION = "FORECAST_GENERATION"
    SHADOW_DECISION = "SHADOW_DECISION"
    EXECUTION = "EXECUTION"
    SETTLEMENT = "SETTLEMENT"
    RECONCILIATION = "RECONCILIATION"
    RISK_MONITORING = "RISK_MONITORING"


class EconomicJobKey(BaseModel):
    """Stable business identity; independent from scheduler attempts and run IDs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    domain: Annotated[str, Field(min_length=1, max_length=128)]
    event_id: Annotated[str, Field(min_length=1, max_length=256)]
    market: Annotated[str, Field(min_length=1, max_length=256)]
    decision_stage: Annotated[str, Field(min_length=1, max_length=128)]
    logical_time: datetime

    @field_validator("logical_time")
    @classmethod
    def logical_time_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("logical_time must include a timezone")
        return value.astimezone(UTC)

    def canonical(self) -> str:
        parts = (
            self.domain,
            self.event_id,
            self.market,
            self.decision_stage,
            self.logical_time.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        )
        return "\x1f".join(parts)


class KillSwitchLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_daily_loss: Annotated[float, Field(ge=0)] | None = None
    max_drawdown: Annotated[float, Field(ge=0)] | None = None
    max_balance_difference: Annotated[float, Field(ge=0)] | None = None
    max_latency_ms: Annotated[float, Field(ge=0)] | None = None
    max_correlated_exposure: Annotated[float, Field(ge=0)] | None = None


class RiskSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_loss: float = 0
    drawdown: float = 0
    settlement_healthy: bool = True
    balance_difference: float = 0
    odds_source_healthy: bool = True
    model_recognized: bool = True
    dataset_recognized: bool = True
    latency_ms: float = 0
    drift_detected: bool = False
    correlated_exposure: float = 0


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["local"] = "local"
    root: Path = Field(default_factory=lambda: Path.home() / ".local" / "state" / "predictor-ops")
    lock_stale_after_seconds: Annotated[float, Field(gt=0)] = 86_400


class JobConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
    command: Annotated[list[str], Field(min_length=1)]
    cwd: Path | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: Annotated[float, Field(gt=0)] = 3600
    heartbeat_interval_seconds: Annotated[float, Field(gt=0)] = 30
    max_output_bytes: Annotated[int, Field(ge=0)] = 10 * 1024 * 1024
    expected_artifact: Path | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    provenance_mode: Literal["strict", "permissive"] = "permissive"
    scientific_state: str | None = None
    job_type: JobType | None = None
    economic_key: EconomicJobKey | None = None
    capital_permission: bool = False
    kill_switch_limits: KillSwitchLimits = Field(default_factory=KillSwitchLimits)
    risk_snapshot: RiskSnapshot | None = None
    exit_statuses: dict[int, RunStatus] = Field(default_factory=lambda: {0: RunStatus.SUCCEEDED, 2: RunStatus.PARTIAL})
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @field_validator("command")
    @classmethod
    def command_has_no_nul(cls, value: list[str]) -> list[str]:
        if any("\0" in part for part in value):
            raise ValueError("command arguments cannot contain NUL")
        return value

    @field_validator("exit_statuses")
    @classmethod
    def exit_statuses_are_valid(cls, value: dict[int, RunStatus]) -> dict[int, RunStatus]:
        if any(code < 0 or code > 255 for code in value):
            raise ValueError("exit status codes must be between 0 and 255")
        return value

    @field_validator("scientific_state")
    @classmethod
    def scientific_state_is_opaque_but_nonempty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("scientific_state must be a non-empty consumer-defined string")
        return value

    @model_validator(mode="after")
    def capital_permission_is_isolated(self) -> JobConfig:
        if self.capital_permission and self.job_type is not JobType.EXECUTION:
            raise ValueError("capital_permission is allowed only for EXECUTION jobs")
        if self.job_type is JobType.EXECUTION and not self.capital_permission:
            raise ValueError("EXECUTION jobs require capital_permission=true")
        return self


class JobsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1", "2"] = "1"
    jobs: list[JobConfig]

    @model_validator(mode="after")
    def unique_ids(self) -> JobsFile:
        ids = [job.id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("job ids must be unique")
        if self.schema_version == "2":
            if any(job.job_type is None or job.economic_key is None for job in self.jobs):
                raise ValueError("schema v2 requires job_type and economic_key for every job")
            keys = [job.economic_key.canonical() for job in self.jobs if job.economic_key]
            if len(keys) != len(set(keys)):
                raise ValueError("economic job keys must be unique")
        return self
