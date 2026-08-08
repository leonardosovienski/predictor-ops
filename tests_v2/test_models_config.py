import json

import pytest
from pydantic import ValidationError

from predictor_ops.config import FileJobConfigSource, HttpJobConfigSource, load_job
from predictor_ops.models import JobConfig, JobsFile, RunStatus, RuntimeConfig


def test_taxonomy_is_complete():
    assert {state.value for state in RunStatus} == {
        "SUCCEEDED",
        "PARTIAL",
        "DEGRADED",
        "SOURCE_UNAVAILABLE",
        "CONFIGURATION_ERROR",
        "FAILED",
        "SKIPPED",
        "WAITING",
    }


def test_scientific_state_is_opaque_and_separate():
    job = JobConfig(id="x", command=["echo"], scientific_state="COLLECTION_ONLY")
    assert job.scientific_state == "COLLECTION_ONLY"
    with pytest.raises(ValidationError):
        JobConfig(id="x", command=["echo"], scientific_state=" ")


def test_config_is_strict_and_unique(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"schema_version": "1", "jobs": [{"id": "x", "command": ["echo"], "oops": 1}]}))
    with pytest.raises(ValidationError):
        FileJobConfigSource(path).load()
    with pytest.raises(ValidationError):
        JobsFile(jobs=[JobConfig(id="x", command=["a"]), JobConfig(id="x", command=["b"])])


def test_redis_requires_url_and_external_requires_https():
    with pytest.raises(ValidationError):
        RuntimeConfig(backend="redis")
    with pytest.raises(ValueError, match="HTTPS"):
        HttpJobConfigSource("http://example.test/jobs")


def test_load_job_missing(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"schema_version": "1", "jobs": []}))
    with pytest.raises(KeyError, match="job not found"):
        load_job(path, "missing")
