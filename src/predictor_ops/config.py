from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen

from pydantic import TypeAdapter

from .models import JobConfig, JobsFile


class JobConfigSource(Protocol):
    def load(self) -> JobsFile: ...


def _validate(raw: bytes | str) -> JobsFile:
    return TypeAdapter(JobsFile).validate_json(raw)


class FileJobConfigSource:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> JobsFile:
        return _validate(self.path.read_bytes())


class HttpJobConfigSource:
    """Validated read-only external source; authentication is supplied by injected headers."""

    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: float = 10) -> None:
        if not url.startswith("https://"):
            raise ValueError("external job configuration requires HTTPS")
        self.url, self.headers, self.timeout = url, headers or {}, timeout

    def load(self) -> JobsFile:
        request = Request(self.url, headers=self.headers)
        with urlopen(request, timeout=self.timeout) as response:
            return _validate(response.read())


def load_job(path: Path, job_id: str) -> JobConfig:
    jobs = FileJobConfigSource(path).load().jobs
    try:
        return next(job for job in jobs if job.id == job_id)
    except StopIteration as exc:
        raise KeyError(f"job not found: {json.dumps(job_id)}") from exc
