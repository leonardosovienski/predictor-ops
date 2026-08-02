from pathlib import Path

import pytest

from predictor_ops.compat.vendor_audit import audit_vendor, tree_digest


def _tree(root: Path, values: dict[str, bytes]):
    for relative, content in values.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def test_identical_report_and_digest_are_deterministic(tmp_path):
    canonical, vendor = tmp_path / "canonical", tmp_path / "vendor"
    values = {"a.py": b"a\n", "nested/b.py": b"b\n"}
    _tree(canonical, values)
    _tree(vendor, dict(reversed(list(values.items()))))
    first, second = audit_vendor(canonical, vendor), audit_vendor(canonical, vendor)
    assert first == second and first["status"] == "IDENTICAL"
    assert tree_digest(canonical) == tree_digest(vendor)


def test_missing_extra_changed_newline_and_bom_diagnostics(tmp_path):
    canonical, vendor = tmp_path / "canonical", tmp_path / "vendor"
    _tree(canonical, {"missing": b"x", "changed": b"a", "newline": b"a\n", "bom": b"value"})
    _tree(vendor, {"extra": b"x", "changed": b"b", "newline": b"a\r\n", "bom": b"\xef\xbb\xbfvalue"})
    report = audit_vendor(canonical, vendor)
    assert report["status"] == "MISMATCH"
    assert report["missing"] == ["missing"] and report["extra"] == ["extra"]
    assert report["diagnostics"] == {
        "bom": ["BOM_ONLY"],
        "changed": ["BYTE_MISMATCH"],
        "newline": ["NEWLINE_ONLY"],
    }


def test_missing_root_fails_closed_and_never_writes(tmp_path):
    canonical, vendor = tmp_path / "canonical", tmp_path / "vendor"
    vendor.mkdir()
    with pytest.raises(ValueError, match="not a directory"):
        audit_vendor(canonical, vendor)
    assert list(vendor.iterdir()) == []
