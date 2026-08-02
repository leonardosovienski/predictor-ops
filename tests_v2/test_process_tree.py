import ctypes
import json
import os
import sys
import time
from pathlib import Path

from predictor_ops.models import JobConfig, OperationalState, RuntimeConfig
from predictor_ops.runner import run_job


def _alive(pid: int) -> bool:
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists() and stat.read_text().split()[2] == "Z":
            return False
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _write_tree_scripts(root: Path) -> Path:
    grandchild = root / "grand child.py"
    child = root / "child process.py"
    parent = root / "parent process.py"
    grandchild.write_text(
        "import os,signal,time\n"
        "print('PID:'+str(os.getpid()), flush=True)\n"
        "if hasattr(signal,'SIGTERM'): signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    child.write_text(
        "import os,subprocess,sys,time\n"
        "print('PID:'+str(os.getpid()), flush=True)\n"
        f"subprocess.Popen([sys.executable,{str(grandchild)!r}])\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    parent.write_text(
        "import os,subprocess,sys,time\n"
        "print('PID:'+str(os.getpid()), flush=True)\n"
        f"subprocess.Popen([sys.executable,{str(child)!r}])\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    return parent


def test_timeout_kills_real_parent_child_grandchild_with_spaced_paths(tmp_path):
    parent = _write_tree_scripts(tmp_path)
    config = JobConfig(
        id="tree-timeout",
        command=[sys.executable, str(parent)],
        timeout_seconds=1.5,
        heartbeat_interval_seconds=0.05,
        runtime=RuntimeConfig(root=tmp_path / "runtime"),
    )
    result = run_job(config)
    assert result.status is OperationalState.FAILED
    assert result.record["termination"]["reason"] == "timeout"
    pids = [
        int(line.removeprefix("PID:"))
        for line in result.record["output"]["text"].splitlines()
        if line.startswith("PID:")
    ]
    assert len(pids) == 3, json.dumps(result.record)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(_alive(pid) for pid in pids):
        time.sleep(0.05)
    assert not any(_alive(pid) for pid in pids), pids
