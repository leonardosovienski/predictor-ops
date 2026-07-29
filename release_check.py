"""Read-only release verification for the standalone ``tools`` repository."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent


def _run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode:
        raise RuntimeError(f"verification command failed ({completed.returncode}): {' '.join(command)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify tools in its workspace and an isolated clone.")
    parser.add_argument("--workspace", type=Path, default=WORKSPACE,
                        help="workspace containing the tools checkout (default: parent of this file)")
    args = parser.parse_args([] if argv is None else argv)
    workspace = args.workspace.resolve()
    try:
        _run([sys.executable, "-m", "pytest", "tools/tests", "-q"], workspace)
        with tempfile.TemporaryDirectory(prefix="tools-release-check-") as temporary:
            base, clone = Path(temporary), Path(temporary) / "tools"
            _run(["git", "clone", "--quiet", str(ROOT), str(clone)], ROOT)
            _run([sys.executable, "-m", "pytest", "tools/tests", "-q"], base)
            probe = subprocess.run(
                [sys.executable, "-c", "from tools.tools_provenance import collect_tools_provenance; import json; print(json.dumps(collect_tools_provenance(), sort_keys=True))"],
                cwd=base, capture_output=True, text=True, check=False,
            )
            if probe.returncode:
                raise RuntimeError(probe.stderr.strip() or "strict provenance validation failed in clone")
            print(json.dumps({"workspace_tests": "passed", "isolated_clone_tests": "passed", "clone_provenance": json.loads(probe.stdout)}, sort_keys=True))
        return 0
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"release verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
