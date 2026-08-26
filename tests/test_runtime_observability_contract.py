from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROL = (ROOT / "scripts" / "ops" / "scp_247_control.ps1").read_text(encoding="utf-8")
SUPERVISOR = (ROOT / "scripts" / "ops" / "scp_247_supervisor.ps1").read_text(encoding="utf-8")


def test_control_status_handles_scheduled_task_min_values_without_method_call():
    assert "$info -and $info.LastRunTime -and $info.LastRunTime.Year -gt 1" in CONTROL
    assert "$info -and $info.NextRunTime -and $info.NextRunTime.Year -gt 1" in CONTROL


def test_supervisor_uses_immutable_per_start_log_paths_and_ledger_provenance():
    assert "$logRunId =" in SUPERVISOR
    assert '"$($Service.Name).$logRunId.out.log"' in SUPERVISOR
    assert '"$($Service.Name).$logRunId.err.log"' in SUPERVISOR
    assert "stdout_log = [IO.Path]::GetFileName($stdout)" in SUPERVISOR
    assert "stderr_log = [IO.Path]::GetFileName($stderr)" in SUPERVISOR
    assert '"$($Service.Name).out.log"' not in SUPERVISOR
    assert '"$($Service.Name).err.log"' not in SUPERVISOR
