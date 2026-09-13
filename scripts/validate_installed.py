"""Run outside the checkout with the installed wheel, using synthetic jobs only."""

import json
import sys
import tempfile
import threading
from pathlib import Path

import predictor_ops
from predictor_ops import JobConfig, RunStatus, run_job
from predictor_ops.provenance import collect_provenance


def main():
    identity = collect_provenance(strict=True)
    assert "site-packages" in str(Path(predictor_ops.__file__).resolve())
    results = []
    with tempfile.TemporaryDirectory(prefix="ops-wheel-") as directory:
        root = Path(directory)
        for name, code, expected, timeout in (
            ("success", "print('ok')", 0, 10),
            ("partial", "raise SystemExit(2)", 2, 10),
            ("failure", "raise SystemExit(9)", 9, 10),
            ("timeout", "import time; time.sleep(30)", 124, 0.2),
            ("interruption", "import time; time.sleep(30)", 130, 10),
        ):
            stop = threading.Event()
            if name == "interruption":
                stop.set()
            job = JobConfig(
                id=name,
                command=[sys.executable, "-c", code],
                runtime={"root": root},
                timeout_seconds=timeout,
                heartbeat_interval_seconds=0.02,
                provenance_mode="strict",
            )
            result = run_job(job, shutdown=stop)
            assert result.exit_code == expected, result
            record = json.loads((root / name / "heartbeat.json").read_text())
            assert record == result.record
            assert len((root / name / "events.jsonl").read_text().splitlines()) == 1
            assert not (root / name / "run.lock").exists()
            results.append({"case": name, "status": result.run_status, "exit_code": result.exit_code})
        artifact = root / "reusable.txt"
        artifact.write_text("controlled existing artifact")
        job = JobConfig(
            id="reuse",
            command=[sys.executable, "-c", "print('reuse')"],
            runtime={"root": root},
            expected_artifact=artifact,
        )
        assert run_job(job).run_status is RunStatus.SUCCEEDED
        assert run_job(job).run_status is RunStatus.SUCCEEDED
        assert artifact.read_text() == "controlled existing artifact"
    assert not [thread for thread in threading.enumerate() if thread.name.startswith("predictor-ops-output-")]
    print(
        json.dumps(
            {
                "version": predictor_ops.__version__,
                "module": predictor_ops.__file__,
                "identity": identity,
                "results": results,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
