import json
import os
import subprocess
import sys
from pathlib import Path

from predictor_ops import cli
from predictor_ops.models import RunStatus
from predictor_ops.runner import RunResult


def test_cli_validate_and_run_outside_checkout(tmp_path):
    config = tmp_path / "jobs.json"
    runtime = tmp_path / "runtime"
    config.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "jobs": [
                    {
                        "id": "smoke",
                        "command": [sys.executable, "-c", "print('wheel-ok')"],
                        "runtime": {"root": str(runtime)},
                    }
                ],
            }
        )
    )
    if os.name == "nt":
        scripts = Path(sys.executable).parent
        if scripts.name.casefold() != "scripts":
            scripts /= "Scripts"
        executable = scripts / "predictor-ops.exe"
    else:
        executable = Path(sys.executable).with_name("predictor-ops")
    validate = subprocess.run([executable, "validate", str(config)], cwd=tmp_path, capture_output=True, text=True)
    assert validate.returncode == 0 and json.loads(validate.stdout)["valid"]
    run = subprocess.run(
        [executable, "run", "--config", str(config), "--job", "smoke"], cwd=tmp_path, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    assert json.loads((runtime / "smoke" / "heartbeat.json").read_text())["run_status"] == "SUCCEEDED"


def test_no_tools_namespace_required(tmp_path):
    probe = "import predictor_ops,importlib.util; assert importlib.util.find_spec('tools') is None"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-I", "-c", probe], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_cli_main_paths(tmp_path, monkeypatch, capsys):
    config = tmp_path / "jobs.json"
    config.write_text(json.dumps({"schema_version": "1", "jobs": [{"id": "x", "command": ["echo", "ok"]}]}))
    assert cli.main(["validate", str(config)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]

    seen = []

    def fake_run(job, shutdown):
        seen.append(job)
        return RunResult("run", RunStatus.SUCCEEDED, 0, {})

    monkeypatch.setattr(cli, "run_job", fake_run)
    runtime = tmp_path / "runtime"
    assert cli.main(["run", "--config", str(config), "--job", "x", "--runtime-root", str(runtime)]) == 0
    assert seen[-1].runtime.root == runtime
    assert cli.main(["run", "--command", sys.executable, "-V"]) == 0
    assert seen[-1].command[-1] == "-V"


def test_cli_provenance_is_strict_and_machine_readable(tmp_path, monkeypatch, capsys):
    seen = []

    def fake_collect(*, strict, source_root=None):
        seen.append((strict, source_root))
        return {"identity_status": "VALIDATED", "kind": "source"}

    monkeypatch.setattr(cli, "collect_provenance", fake_collect)
    assert cli.main(["provenance", "--source-root", str(tmp_path)]) == 0
    assert seen == [(True, tmp_path)]
    assert json.loads(capsys.readouterr().out) == {
        "identity_status": "VALIDATED",
        "kind": "source",
    }


def test_cli_provenance_fails_closed(monkeypatch, capsys):
    def fail(**_kwargs):
        raise RuntimeError("identity unavailable")

    monkeypatch.setattr(cli, "collect_provenance", fail)
    assert cli.main(["provenance"]) == 3
    error = json.loads(capsys.readouterr().err)
    assert error == {"error": "identity unavailable", "status": "CONFIGURATION_ERROR"}


def test_cli_configuration_errors(tmp_path, capsys):
    missing = tmp_path / "missing.json"
    assert cli.main(["run", "--config", str(missing), "--job", "x"]) == 3
    assert json.loads(capsys.readouterr().err)["status"] == "CONFIGURATION_ERROR"
