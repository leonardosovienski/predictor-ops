from pathlib import Path

ROOT = Path(__file__).parents[1]
EXPECTED = {
    "install_collection_only_tasks.ps1",
    "install_predictor_gate_monitor_task.ps1",
    "install_task_health_monitor_task.ps1",
    "monitor_predictor_gates.ps1",
    "monitor_task_health.ps1",
}


def test_all_removed_windows_operations_have_isolated_ascii_transition_assets():
    directory = ROOT / "migration" / "windows"
    scripts = {path.name for path in directory.glob("*.ps1")}
    assert scripts == EXPECTED
    for path in directory.glob("*.ps1"):
        path.read_bytes().decode("ascii")


def test_transition_assets_are_excluded_from_wheel_configuration():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'packages = ["src/predictor_ops"]' in pyproject
    assert "migration/windows" not in pyproject
