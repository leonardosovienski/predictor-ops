import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vendor_byte_audit as audit


def make_core(root: Path) -> Path:
    core = root / "predictor_core"
    (core / "kernel").mkdir(parents=True)
    (core / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (core / "__init__.py").write_bytes(b"VALUE = 1\n")
    (core / "kernel" / "logic.py").write_bytes(b"def value():\n    return 1\n")
    (core / "README.md").write_text("not payload", encoding="utf-8")
    (core / "tests").mkdir()
    (core / "tests" / "test_ignored.py").write_text("raise AssertionError", encoding="utf-8")
    return core


def make_vendor(workspace: Path, core: Path, name: str = "consumer") -> Path:
    vendor = workspace / name / "vendor" / "predictor_core"
    for source in audit.payload_entries(core).values():
        target = vendor / source.path.relative_to(core)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.path.read_bytes())
    manifest = audit.aggregate(audit.payload_entries(core))
    files = {key: entry.sha256 for key, entry in audit.payload_entries(core).items()}
    (vendor / audit.MANIFEST_NAME).write_text(
        json.dumps({"files": files, "aggregate": manifest, "source_version": "1.0.0"}), encoding="utf-8"
    )
    return vendor


def test_identical_and_deterministic_report(tmp_path: Path):
    core = make_core(tmp_path)
    make_vendor(tmp_path, core)
    first = audit.report(tmp_path, core)
    second = audit.report(tmp_path, core)
    assert first == second
    assert first["exit_code"] == 0
    assert first["consumers"][0]["status"] == "IDENTICAL"


def test_changed_file_and_newline_diagnostic(tmp_path: Path):
    core = make_core(tmp_path)
    vendor = make_vendor(tmp_path, core)
    (vendor / "kernel" / "logic.py").write_bytes(b"def value():\r\n    return 1\r\n")
    result = audit.audit_vendor("consumer", vendor, core)
    assert result["status"] == "DRIFT"
    assert result["changed_files"][0]["text_diagnostic"]["kind"] == "NEWLINE_ONLY"


def test_bom_only_is_diagnostic_not_normalized_identity(tmp_path: Path):
    core = make_core(tmp_path)
    vendor = make_vendor(tmp_path, core)
    logic = vendor / "kernel" / "logic.py"
    logic.write_bytes(b"\xef\xbb\xbf" + logic.read_bytes())
    result = audit.audit_vendor("consumer", vendor, core)
    assert result["status"] == "DRIFT"
    assert result["changed_files"][0]["text_diagnostic"]["kind"] == "BOM_ONLY"


def test_missing_extra_and_manifest_mismatch_precedence(tmp_path: Path):
    core = make_core(tmp_path)
    vendor = make_vendor(tmp_path, core)
    (vendor / "kernel" / "logic.py").unlink()
    (vendor / "extra.py").write_text("x = 1\n", encoding="utf-8")
    result = audit.audit_vendor("consumer", vendor, core)
    assert result["status"] == "INCOMPLETE"
    assert result["missing_files"] == ["kernel/logic.py"]
    assert result["extra_files"] == ["extra.py"]
    assert result["manifest_issues"]


def test_manifest_incorrect_and_missing_vendor(tmp_path: Path):
    core = make_core(tmp_path)
    vendor = make_vendor(tmp_path, core)
    manifest = vendor / audit.MANIFEST_NAME
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["aggregate"] = "bad"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert audit.audit_vendor("consumer", vendor, core)["status"] == "MANIFEST_MISMATCH"
    manifest.unlink()
    assert audit.audit_vendor("consumer", vendor, core)["status"] == "MANIFEST_MISMATCH"
    missing = audit.audit_vendor("absent", tmp_path / "absent" / "vendor" / "predictor_core", core)
    assert missing["status"] == "NOT_VERIFIABLE"
    assert audit.audit_vendor("consumer", vendor, tmp_path / "missing-core")["status"] == "ERROR"


def test_multiple_consumers_exit_code_and_no_vendor_writes(tmp_path: Path):
    core = make_core(tmp_path)
    good = make_vendor(tmp_path, core, "good")
    bad = make_vendor(tmp_path, core, "bad")
    target = bad / "__init__.py"
    target.write_text("VALUE = 2\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in good.rglob("*") if path.is_file()}
    data = audit.report(tmp_path, core)
    after = {path: path.read_bytes() for path in good.rglob("*") if path.is_file()}
    assert data["exit_code"] == 1
    assert data["summary"]["statuses"] == {"DRIFT": 1, "IDENTICAL": 1}
    assert before == after


def test_type_difference_and_read_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    core = make_core(tmp_path)
    vendor = make_vendor(tmp_path, core)
    candidate = vendor / "kernel" / "logic.py"
    original_kind = audit._kind

    def synthetic_symlink(path: Path):
        if path == candidate:
            return "symlink"
        return original_kind(path)

    monkeypatch.setattr(audit, "_kind", synthetic_symlink)
    result = audit.audit_vendor("consumer", vendor, core)
    assert result["status"] == "DRIFT"
    assert result["changed_files"][0]["kind"] == "TYPE_DIFFERENT"
    monkeypatch.setattr(audit, "_kind", original_kind)

    original = audit.payload_entries

    def broken(root: Path):
        if root == core:
            raise OSError("synthetic read failure")
        return original(root)

    monkeypatch.setattr(audit, "payload_entries", broken)
    assert audit.audit_vendor("consumer", vendor, core)["status"] == "ERROR"


def test_json_cli_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    core = make_core(tmp_path)
    make_vendor(tmp_path, core)
    assert audit.main(["--workspace", str(tmp_path), "--canonical", str(core), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["statuses"] == {"IDENTICAL": 1}
