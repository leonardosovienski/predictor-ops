from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import threading

import pytest

from tools import operational_runner as runner


def invoke(tmp_path: Path, command: list[str], **extra: object) -> tuple[int, Path, Path, Path]:
    log = tmp_path / "human.log"
    heartbeat = tmp_path / "heartbeat.json"
    events = tmp_path / "events.jsonl"
    args = ["run", "--task", "test-task", "--project", "test", "--cwd", str(tmp_path), "--log", str(log), "--heartbeat", str(heartbeat), "--event-log", str(events), "--provenance-mode", "permissive"]
    for key, value in extra.items():
        args.extend(["--" + key.replace("_", "-"), str(value)])
    args.extend(["--", *command])
    return runner.main(args), log, heartbeat, events


def read_heartbeat(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_success_records_observable_envelope(tmp_path: Path) -> None:
    code, log, heartbeat, events = invoke(tmp_path, [sys.executable, "-c", "print('ok')"])
    record = read_heartbeat(heartbeat)
    assert code == 0 and record["status"] == "SUCCEEDED"
    assert record["started_at_utc"] and record["finished_at_utc"]
    assert "ok" in log.read_text(encoding="utf-8")
    assert json.loads(events.read_text(encoding="utf-8"))["exit_code"] == 0
    assert record["tools_provenance"]["version"] == Path(runner.__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
    assert json.loads(events.read_text(encoding="utf-8"))["tools_provenance"] == record["tools_provenance"]


def test_child_failure_is_propagated(tmp_path: Path) -> None:
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(7)"])
    assert code == 7
    assert read_heartbeat(heartbeat)["status"] == "FAILED"


def test_timeout_is_observable(tmp_path: Path) -> None:
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05)
    assert code == 124
    assert read_heartbeat(heartbeat)["status"] == "TIMED_OUT"


def test_lock_skips_second_instance(tmp_path: Path) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    lock = heartbeat.with_suffix(".json.lock")
    lock.write_text("already running", encoding="ascii")
    code, _, actual_heartbeat, events = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(0)"])
    assert code == 4
    assert actual_heartbeat == heartbeat
    sidecar = runner.skipped_heartbeat_path(heartbeat)
    assert read_heartbeat(sidecar)["status"] == "SKIPPED"
    assert json.loads(events.read_text(encoding="utf-8"))["status"] == "SKIPPED"


def test_lock_loser_never_touches_winner_heartbeat(tmp_path: Path) -> None:
    # Regressão OP-1: o perdedor da corrida do lock escrevia no MESMO heartbeat
    # do vencedor — o SKIPPED podia sobrescrever o RUNNING/estado final do dono
    # do lock e era a fonte da colisão de os.replace no Windows.
    heartbeat = tmp_path / "heartbeat.json"
    lock = heartbeat.with_suffix(".json.lock")
    lock.write_text(json.dumps({"run_id": "winner", "pid": os.getpid()}), encoding="ascii")
    winner_record = {"status": "RUNNING", "run_id": "winner"}
    runner.write_heartbeat(heartbeat, winner_record)
    code, _, _, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(0)"])
    assert code == 4
    assert read_heartbeat(heartbeat) == winner_record
    assert read_heartbeat(runner.skipped_heartbeat_path(heartbeat))["status"] == "SKIPPED"


def test_missing_expected_artifact_is_partial(tmp_path: Path) -> None:
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(0)"], expected_artifact=tmp_path / "missing.txt")
    assert code == 1
    assert read_heartbeat(heartbeat)["status"] == "PARTIAL"


def test_child_partial_exit_is_preserved_and_observable(tmp_path: Path) -> None:
    code, _, heartbeat, events = invoke(
        tmp_path,
        [sys.executable, "-c", "raise SystemExit(10)"],
        partial_exit_code=10,
    )
    assert code == 10
    assert read_heartbeat(heartbeat)["status"] == "PARTIAL"
    assert json.loads(events.read_text(encoding="utf-8"))["exit_code"] == 10


def test_consumer_source_unavailable_status_reaches_heartbeat(tmp_path: Path) -> None:
    status = tmp_path / "consumer-status.json"
    heartbeat = tmp_path / "heartbeat.json"
    log, events = tmp_path / "human.log", tmp_path / "events.jsonl"
    child = f"from pathlib import Path; Path(r'{status}').write_text('{{\"status\":\"SOURCE_UNAVAILABLE\",\"reason\":\"UPSTREAM_INPUT_MISSING\"}}')"
    code = runner.main(["run", "--task", "source", "--project", "test", "--cwd", str(tmp_path), "--log", str(log), "--heartbeat", str(heartbeat), "--event-log", str(events), "--consumer-status-json", str(status), "--provenance-mode", "permissive", "--", sys.executable, "-c", child])
    record = read_heartbeat(heartbeat)
    assert code == 0 and record["status"] == "SOURCE_UNAVAILABLE"
    assert record["operational_status"]["reason"] == "UPSTREAM_INPUT_MISSING"


def test_invalid_working_directory_is_observable(tmp_path: Path) -> None:
    log, heartbeat, events = tmp_path / "x.log", tmp_path / "x.json", tmp_path / "x.jsonl"
    code = runner.main(["run", "--task", "bad", "--project", "test", "--cwd", str(tmp_path / "absent"), "--log", str(log), "--heartbeat", str(heartbeat), "--event-log", str(events), "--provenance-mode", "permissive", "--", sys.executable, "-c", "pass"])
    assert code == 3 and read_heartbeat(heartbeat)["status"] == "FAILED"


def test_missing_child_script_is_observable(tmp_path: Path) -> None:
    code, _, heartbeat, _ = invoke(tmp_path, [str(tmp_path / "missing-program.exe")])
    assert code == 3
    assert read_heartbeat(heartbeat)["status"] == "FAILED"


def test_atomic_heartbeat_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.json"
    runner.write_heartbeat(path, {"status": "STARTED"})
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "STARTED"
    assert not list(tmp_path.glob(".heartbeat.json.*.tmp"))


def test_atomic_write_json_leaves_no_orphan_temp_file_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regressão: uma falha entre a criação do tempfile e o os.replace (disco
    # cheio, processo morto no meio) deixava um .{name}.{uuid}.tmp órfão —
    # inconsistente com o cleanup já usado em tools/release_manifest.py.
    path = tmp_path / "heartbeat.json"

    def _boom(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(runner.os, "fsync", _boom)
    with pytest.raises(OSError):
        runner.atomic_write_json(path, {"status": "STARTED"})
    assert not path.exists()  # real file never touched (os.replace never ran)
    assert not list(tmp_path.glob(".heartbeat.json.*.tmp"))  # no orphan left


def test_secrets_are_redacted_from_record(tmp_path: Path) -> None:
    _, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(2)", "token=visible"])
    assert "visible" not in heartbeat.read_text(encoding="utf-8")
    assert "token=[REDACTED]" in heartbeat.read_text(encoding="utf-8")


def test_human_log_has_boundary_even_when_child_is_silent(tmp_path: Path) -> None:
    code, log, _, _ = invoke(tmp_path, [sys.executable, "-c", "pass"])
    assert code == 0
    assert "STARTED" in log.read_text(encoding="utf-8") and "SUCCEEDED" in log.read_text(encoding="utf-8")


def test_runner_creates_missing_lock_parent(tmp_path: Path) -> None:
    base = tmp_path / "operations"
    code = runner.main(["run", "--task", "nested", "--project", "test", "--cwd", str(tmp_path), "--log", str(base / "human.log"), "--heartbeat", str(base / "heartbeat.json"), "--event-log", str(base / "events.jsonl"), "--provenance-mode", "permissive", "--", sys.executable, "-c", "pass"])
    assert code == 0
    assert (base / "heartbeat.json").is_file() and not (base / "heartbeat.json.lock").exists()


def test_consumer_metadata_is_additive_and_redacted(tmp_path: Path) -> None:
    metadata = json.dumps({"project": "example", "project_commit": "abc", "token": "do-not-persist"})
    code, _, heartbeat, _ = invoke(
        tmp_path, [sys.executable, "-c", "pass"], consumer_provenance_json=metadata,
    )
    record = read_heartbeat(heartbeat)
    assert code == 0
    assert record["consumer_provenance"]["project_commit"] == "abc"
    assert record["consumer_provenance"]["token"] == "[REDACTED]"


def test_strict_setup_failure_is_published_as_a_failed_operational_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "collect_tools_provenance", lambda **_: (_ for _ in ()).throw(runner.ToolsProvenanceError("manifest invalid")))
    log, heartbeat, events = tmp_path / "human.log", tmp_path / "heartbeat.json", tmp_path / "events.jsonl"
    code = runner.main(["run", "--task", "strict", "--project", "test", "--cwd", str(tmp_path), "--log", str(log), "--heartbeat", str(heartbeat), "--event-log", str(events), "--", sys.executable, "-c", "pass"])
    record = read_heartbeat(heartbeat)
    assert code == 3 and record["status"] == "FAILED"
    assert record["tools_provenance"]["status"] == "UNAVAILABLE"
    assert json.loads(events.read_text(encoding="utf-8"))["exit_code"] == 3


def test_stale_lock_is_reclaimed_but_recent_lock_is_preserved(tmp_path: Path) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    lock = heartbeat.with_suffix(".json.lock")
    lock.write_text("orphan", encoding="ascii")
    old = time.time() - 86401
    os.utime(lock, (old, old))
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "pass"])
    assert code == 0 and not lock.exists()
    assert read_heartbeat(heartbeat)["lock"]["reclaimed"] is True
    assert read_heartbeat(heartbeat)["lock"]["reclaimed_reason"] == "age_exceeded"


def test_lock_with_dead_owner_pid_is_reclaimed_immediately_even_when_young(tmp_path: Path) -> None:
    # Regressão (auditoria hostil 2026-07-17): antes, um lock órfão por kill
    # duro (queda de energia, OOM-killer, timeout do scheduler) ficava preso
    # até o TETO DE IDADE inteiro (24h por padrão), mesmo com o PID dono
    # comprovadamente morto — em agendamento diário isso podia pular 2 dias
    # seguidos por um único evento de kill duro. Agora, PID morto reclama o
    # lock na hora, independente da idade.
    heartbeat = tmp_path / "heartbeat.json"
    lock = heartbeat.with_suffix(".json.lock")
    lock.write_text(json.dumps({"run_id": "r1", "pid": 999999999,  # PID quase certamente inexistente
                                "created_at_utc": "2026-07-17T00:00:00Z"}), encoding="ascii")
    # lock RECÉM criado (idade ~0s) — MUITO abaixo de qualquer stale_after
    # razoável; só a checagem de PID vivo pode justificar o reclaim aqui.
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "pass"])
    assert code == 0 and not lock.exists()
    record = read_heartbeat(heartbeat)
    assert record["lock"]["reclaimed"] is True
    assert record["lock"]["reclaimed_reason"] == "owner_pid_dead"


def test_lock_with_live_owner_pid_is_not_reclaimed_even_if_unreadable_age_check_would_allow(tmp_path: Path) -> None:
    # PID do próprio processo de teste — garantidamente vivo. O lock não pode
    # ser reclamado mesmo que outro fator sugerisse idade favorável.
    heartbeat = tmp_path / "heartbeat.json"
    lock = heartbeat.with_suffix(".json.lock")
    lock.write_text(json.dumps({"run_id": "r1", "pid": os.getpid(),
                                "created_at_utc": "2026-07-17T00:00:00Z"}), encoding="ascii")
    code, _, actual_heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(0)"])
    assert code == 4  # SKIPPED — lock não foi reclamado
    assert lock.exists()


def test_timeout_uses_process_tree_termination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[int] = []

    def terminate(child):
        observed.append(child.pid)
        child.kill()

    monkeypatch.setattr(runner, "_terminate_process_tree", terminate)
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.01)
    record = read_heartbeat(heartbeat)
    assert code == 124 and observed and record["status"] == "TIMED_OUT"
    assert record["termination"] is None


def test_output_is_bounded_and_remains_redacted(tmp_path: Path) -> None:
    secret = "very-secret-output-value"
    code, log, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", f"print('token={secret}' + 'x' * 100000)"], max_output_bytes=128)
    text = log.read_text(encoding="utf-8")
    record = read_heartbeat(heartbeat)
    assert code == 0 and secret not in text and "[OUTPUT_TRUNCATED]" in text
    assert record["output"]["truncated"] is True and record["output"]["limit_bytes"] == 128


def test_jsonl_append_is_parseable_under_threaded_writers(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    threads = [threading.Thread(target=runner.append_event, args=(events, {"number": index})) for index in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(json.loads(line)["number"] for line in events.read_text(encoding="utf-8").splitlines()) == list(range(40))


def test_atomic_write_retries_transient_windows_permission_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regressão (auditoria hostil 2026-07-17, rodada "tools/"): dois processos
    # perdedores da corrida de lock ainda escrevem heartbeat concorrentemente
    # sem lock nenhum (comportamento pré-existente, não alterado aqui). No
    # Windows, os.replace pode lançar PermissionError (WinError 5) quando o
    # destino está momentaneamente aberto por OUTRO os.replace concorrente —
    # reproduzido em ~1 de cada 3 execuções com 5 threads concorrentes. Isso
    # subia sem tratamento e derrubava a thread/processo chamador em vez de
    # terminar como SKIPPED observável. _replace_with_retry precisa absorver
    # essa colisão transitória.
    target = tmp_path / "heartbeat.json"
    calls = {"n": 0}
    real_replace = os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(runner.os, "replace", flaky_replace)
    runner.atomic_write_json(target, {"status": "ok"})
    assert calls["n"] == 2
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "ok"


def test_atomic_write_gives_up_after_persistent_permission_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "heartbeat.json"

    def always_denied(src, dst):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(runner.os, "replace", always_denied)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    with pytest.raises(PermissionError):
        runner.atomic_write_json(target, {"status": "ok"})
    # nenhum arquivo temporário órfão, mesmo depois de esgotar as tentativas
    assert list(tmp_path.glob(".heartbeat.json.*.tmp")) == []
