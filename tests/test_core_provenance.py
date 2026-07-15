import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core_provenance as provenance
import vendor_byte_audit as byte_audit


def make_core(root: Path, version: str = "1.0.0", value: str = "1") -> Path:
    core = root / "predictor_core"
    core.mkdir(parents=True)
    (core / "VERSION").write_bytes(f"{version}\n".encode())
    (core / "__init__.py").write_bytes(f"VALUE = {value}\n".encode())
    return core


def make_consumer(workspace: Path, core: Path, name: str = "consumer") -> Path:
    vendor = workspace / name / "vendor" / "predictor_core"
    vendor.mkdir(parents=True)
    for entry in byte_audit.payload_entries(core).values():
        destination = vendor / entry.path.relative_to(core)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(entry.path.read_bytes())
    files = {key: value.sha256 for key, value in byte_audit.payload_entries(core).items()}
    (vendor / "CORE_MANIFEST.json").write_text(
        json.dumps({"files": files, "aggregate": byte_audit.aggregate(byte_audit.payload_entries(core)), "source_version": "1.0.0"}),
        encoding="utf-8",
    )
    return workspace / name


def test_expected_vendor_match_and_json_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    core = make_core(tmp_path)
    make_consumer(tmp_path, core)
    report = provenance.build_report(tmp_path, None, mode="vendor", script=None, module=None, full=True, timeout=5, strict=True)
    assert report["exit_code"] == 0
    assert report["consumers"][0]["status"] == "MATCH"
    assert provenance.main(["--workspace", str(tmp_path), "--all", "--json", "--strict"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["statuses"] == {"MATCH": 1}


def test_pythonpath_alternative_path_mismatch_in_script_mode(tmp_path: Path):
    core = make_core(tmp_path / "expected")
    consumer = make_consumer(tmp_path, core)
    alternative_parent = tmp_path / "alternative"
    make_core(alternative_parent, version="1.0.0", value="2")
    script = consumer / "probe.py"
    script.write_text("import predictor_core\n", encoding="utf-8")
    old = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(alternative_parent)
    try:
        result = provenance.audit_consumer("consumer", consumer, mode="script", script=str(script), module=None, full=True, timeout=5)
    finally:
        if old is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = old
    assert result["status"] == "PATH_MISMATCH"


def test_report_mode_does_not_fail_but_strict_does(tmp_path: Path):
    core = make_core(tmp_path / "expected")
    consumer = make_consumer(tmp_path, core)
    alternative_parent = tmp_path / "alternative"
    make_core(alternative_parent, value="2")
    script = consumer / "probe.py"
    script.write_text("import predictor_core\n", encoding="utf-8")
    old = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(alternative_parent)
    try:
        report = provenance.build_report(tmp_path, ["consumer"], mode="script", script=str(script), module=None, full=True, timeout=5, strict=False)
        strict = provenance.build_report(tmp_path, ["consumer"], mode="script", script=str(script), module=None, full=True, timeout=5, strict=True)
    finally:
        if old is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = old
    assert report["consumers"][0]["status"] == "PATH_MISMATCH"
    assert report["exit_code"] == 0
    assert strict["exit_code"] == 1


def test_version_and_hash_mismatch_with_preloaded_module(tmp_path: Path):
    expected = make_core(tmp_path / "expected", version="1.0.0", value="1")
    actual = make_core(tmp_path / "actual", version="2.0.0", value="2")
    module = SimpleNamespace(__file__=str(actual / "__init__.py"))
    result = provenance.inspect_core_provenance(expected, module, full=True)
    assert result["status"] == "PATH_MISMATCH"
    assert not result["version_matches"]
    assert not result["hash_matches"]
    with pytest.raises(provenance.CoreProvenanceError):
        provenance.verify_core_provenance(expected, module, full=True, strict=True)


def test_sys_modules_contamination_is_observed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    expected = make_core(tmp_path / "expected")
    alternative = make_core(tmp_path / "alternative")
    monkeypatch.setitem(sys.modules, "predictor_core", SimpleNamespace(__file__=str(alternative / "__init__.py")))
    result = provenance.inspect_core_provenance(expected, module=None, full=False)
    assert result["status"] == "PATH_MISMATCH"


def test_missing_vendor_not_configured_and_module_not_imported(tmp_path: Path):
    missing = provenance.audit_consumer("missing", tmp_path / "missing", full=True, timeout=5)
    assert missing["status"] == "NOT_CONFIGURED"
    expected = make_core(tmp_path / "expected")
    result = provenance.inspect_core_provenance(expected, module=None, full=False)
    assert result["status"] == "IMPORT_FAILED"


def test_script_and_module_modes(tmp_path: Path):
    core = make_core(tmp_path)
    consumer = make_consumer(tmp_path, core)
    (consumer / "vendor_bootstrap.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent / 'vendor'))\nimport predictor_core\n",
        encoding="utf-8",
    )
    script_result = provenance.audit_consumer("consumer", consumer, mode="script", script=str(consumer / "vendor_bootstrap.py"), module=None, full=True, timeout=5)
    assert script_result["status"] == "MATCH"
    (consumer / "probe_module.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent / 'vendor'))\nimport predictor_core\n",
        encoding="utf-8",
    )
    module_result = provenance.audit_consumer("consumer", consumer, mode="module", script=None, module="probe_module", full=False, timeout=5)
    assert module_result["status"] == "MATCH"


def test_multiple_consumers_no_writes_and_deterministic(tmp_path: Path):
    core = make_core(tmp_path)
    first = make_consumer(tmp_path, core, "first")
    second = make_consumer(tmp_path, core, "second")
    before = {path: path.read_bytes() for root in (first, second) for path in root.rglob("*") if path.is_file()}
    one = provenance.build_report(tmp_path, None, mode="vendor", script=None, module=None, full=True, timeout=5, strict=False)
    two = provenance.build_report(tmp_path, None, mode="vendor", script=None, module=None, full=True, timeout=5, strict=False)
    after = {path: path.read_bytes() for root in (first, second) for path in root.rglob("*") if path.is_file()}
    assert one == two
    assert one["summary"]["statuses"] == {"MATCH": 2}
    assert before == after


def test_symlink_path_matches_when_supported(tmp_path: Path):
    expected = make_core(tmp_path / "expected")
    linked_parent = tmp_path / "linked"
    try:
        os.symlink(expected, linked_parent, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable in this Windows environment")
    module = SimpleNamespace(__file__=str(linked_parent / "__init__.py"))
    assert provenance.inspect_core_provenance(expected, module, full=False)["status"] == "MATCH"
