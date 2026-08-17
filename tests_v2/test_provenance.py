import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import predictor_ops.provenance as provenance
from predictor_ops.provenance import ProvenanceError, _source_identity, collect_provenance, safe_serialize


def _git(root: Path, *args: str):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def test_source_clean_dirty_detached_and_missing_commit(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "file").write_text("one")
    _git(tmp_path, "add", "file")
    _git(tmp_path, "commit", "-m", "initial")
    clean = _source_identity(tmp_path)
    assert clean["identity_status"] == "VALIDATED" and clean["commit"]
    assert collect_provenance(strict=True, source_root=tmp_path)["identity_status"] == "VALIDATED"
    _git(tmp_path, "checkout", "--detach")
    assert _source_identity(tmp_path)["identity_status"] == "VALIDATED"
    (tmp_path / "file").write_text("tampered")
    assert _source_identity(tmp_path)["identity_status"] == "DIRTY"
    assert collect_provenance(strict=False, source_root=tmp_path)["identity_status"] == "DIRTY"
    with pytest.raises(ProvenanceError, match="not validated"):
        collect_provenance(strict=True, source_root=tmp_path)
    with pytest.raises(ProvenanceError, match="commit"):
        _source_identity(tmp_path / "missing")


def test_strict_editable_fails_closed_and_permissive_is_safe():
    with pytest.raises(ProvenanceError, match="editable"):
        collect_provenance(strict=True)
    value = collect_provenance(strict=False)
    assert value["identity_status"] == "UNVERIFIED"
    assert "editable" in safe_serialize(value)


def test_safe_serialization_rejects_unserializable():
    with pytest.raises(ProvenanceError, match="serializable"):
        safe_serialize({"bad": object()})


class FakeDistribution:
    version = "2.0.1"

    def __init__(self, root, files):
        self.root, self.files = root, [Path(item) for item in files]

    def locate_file(self, relative):
        return self.root / str(relative)


def _record_fixture(tmp_path, *, content=b"safe", algorithm="sha256"):
    package = tmp_path / "predictor_ops"
    package.mkdir(parents=True)
    module = package / "module.py"
    module.write_bytes(content)
    metadata = tmp_path / "predictor_ops-2.0.1.dist-info"
    metadata.mkdir()
    record = metadata / "RECORD"
    encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
    record.write_text(f"predictor_ops/module.py,{algorithm}={encoded},{len(content)}\n")
    return FakeDistribution(tmp_path, [module.relative_to(tmp_path), record.relative_to(tmp_path)]), module, record


def test_wheel_record_unit_validation_and_adversarial_failures(tmp_path, monkeypatch):
    fake, module, record = _record_fixture(tmp_path)
    monkeypatch.setattr(provenance, "distribution", lambda name: fake)
    assert provenance._verify_wheel()["verified_files"] == 1
    module.write_bytes(b"tampered")
    with pytest.raises(ProvenanceError, match="failed verification"):
        provenance._verify_wheel()
    fake, _, record = _record_fixture(tmp_path / "second", algorithm="md5")
    monkeypatch.setattr(provenance, "distribution", lambda name: fake)
    with pytest.raises(ProvenanceError, match="unsupported"):
        provenance._verify_wheel()
    record.write_text("predictor_ops/module.py,,\n")
    with pytest.raises(ProvenanceError, match="no verifiable"):
        provenance._verify_wheel()


def test_wheel_missing_record_and_editable_metadata_fail_closed(tmp_path, monkeypatch):
    fake = FakeDistribution(tmp_path, [])
    monkeypatch.setattr(provenance, "distribution", lambda name: fake)
    with pytest.raises(ProvenanceError, match="RECORD"):
        provenance._verify_wheel()
    metadata = tmp_path / "predictor_ops-2.0.1.dist-info"
    metadata.mkdir()
    direct = metadata / "direct_url.json"
    direct.write_text(json.dumps({"dir_info": {"editable": True}}))
    fake = FakeDistribution(tmp_path, [direct.relative_to(tmp_path)])
    monkeypatch.setattr(provenance, "distribution", lambda name: fake)
    with pytest.raises(ProvenanceError, match="editable"):
        provenance._verify_wheel()


@pytest.mark.timeout(120)
def test_wheel_record_tampering_fails_in_isolated_environment(tmp_path):
    dist = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(dist)],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
    )
    wheel = next(dist.glob("*.whl"))
    environment = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([python, "-m", "pip", "install", str(wheel)], check=True, capture_output=True)
    probe = (
        "from predictor_ops.provenance import collect_provenance; "
        "print(collect_provenance(strict=True)['identity_status'])"
    )
    assert (
        subprocess.run([python, "-I", "-c", probe], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
        == "VALIDATED"
    )
    module = next(environment.glob("**/site-packages/predictor_ops/redaction.py"))
    module.write_text(module.read_text() + "\n# tampered\n")
    failed = subprocess.run([python, "-I", "-c", probe], cwd=tmp_path, capture_output=True, text=True)
    assert failed.returncode != 0 and "failed verification" in failed.stderr
