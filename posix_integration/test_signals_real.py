import json
import os
import signal
import subprocess
import sys
import time

import pytest


def test_sigterm_reaches_cli_and_kills_child(tmp_path):
    runtime = tmp_path / "runtime"
    child = "import os,time; print('PID:'+str(os.getpid()),flush=True); time.sleep(30)"
    with subprocess.Popen(
        [
            sys.executable,
            "-m",
            "predictor_ops",
            "run",
            "--job-id",
            "signal",
            "--runtime-root",
            str(runtime),
            "--command",
            sys.executable,
            "-c",
            child,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        heartbeat = runtime / "signal" / "heartbeat.json"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not heartbeat.exists():
            time.sleep(0.05)
        assert heartbeat.exists()
        child_pid = json.loads(heartbeat.read_text())["pid"]
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=10)
        assert process.returncode == 130
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
