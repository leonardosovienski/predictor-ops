"""Skip consumer-integration tests when tools is cloned in isolation.

The shared utility unit tests must be reproducible from the tools repository.
Entry-point contract tests intentionally exercise sibling consumers and run only
when the workspace layout is present.
"""
from __future__ import annotations

from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_CONSUMERS = ("brasileirao-predictor", "cs-predictor", "lol-predictor")


def pytest_collection_modifyitems(config, items):
    if all((_ROOT / consumer).is_dir() for consumer in _CONSUMERS):
        return
    marker = pytest.mark.skip(reason="requires sibling consumer workspace")
    for item in items:
        if item.fspath.basename in {
            "test_brasileirao_operational_entrypoint.py",
            "test_cs_operational_entrypoint.py",
            "test_lol_operational_entrypoint.py",
        }:
            item.add_marker(marker)
