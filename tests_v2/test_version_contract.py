import re
import tomllib
from pathlib import Path


def test_changelog_latest_release_matches_package_version():
    root = Path(__file__).parents[1]
    with (root / "pyproject.toml").open("rb") as handle:
        package_version = tomllib.load(handle)["project"]["version"]
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = re.search(r"^##\s+\[?([0-9]+\.[0-9]+\.[0-9]+)\]?", changelog, re.MULTILINE)
    assert latest is not None, "CHANGELOG has no release heading"
    assert latest.group(1) == package_version
