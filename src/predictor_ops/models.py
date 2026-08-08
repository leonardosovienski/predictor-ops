from __future__ import annotations

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


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["local", "redis"] = "local"
    root: Path = Field(default_factory=lambda: Path.home() / ".local" / "state" / "predictor-ops")
    redis_url: str | None = None
    namespace: str = "predictor_ops"
    lock_stale_after_seconds: Annotated[float, Field(gt=0)] = 86_400

    @model_validator(mode="after")
    def require_redis_url(self) -> RuntimeConfig:
        if self.backend == "redis" and not self.redis_url:
            raise ValueError("redis_url is required for the redis backend")
        return self


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


class JobsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"
    jobs: list[JobConfig]

    @model_validator(mode="after")
    def unique_ids(self) -> JobsFile:
        ids = [job.id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("job ids must be unique")
        return self
