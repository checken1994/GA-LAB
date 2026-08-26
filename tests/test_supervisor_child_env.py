from pathlib import Path


REQUIRED_CHILD_SAFE_LINES = {
    "SCP_EVOLUTION_AUTO=0",
    "SCP_EVOLUTION_ENABLED=0",
    "SCP_WHY_LLM_ENABLED=0",
    "SCP_SUBSYSTEM_TELEMETRY_ENABLED=1",
    "SCP_FAST_LEARNING_CYCLE_TIMEOUT_SECONDS=300",
}


def test_supervisor_recreates_required_child_safe_boundaries():
    root = Path(__file__).resolve().parents[1]
    supervisor = (root / "scripts" / "ops" / "scp_247_supervisor.ps1").read_text(encoding="utf-8")
    for line in REQUIRED_CHILD_SAFE_LINES:
        assert f"'{line}'" in supervisor


def test_dashboard_receives_scheduler_admin_boundary():
    root = Path(__file__).resolve().parents[1]
    supervisor = (root / "scripts" / "ops" / "scp_247_supervisor.ps1").read_text(encoding="utf-8")
    assert "'dashboard'))" in supervisor
    assert "$env:SCP_SCHEDULER_ADMIN_TOKEN = $adminToken" in supervisor
    assert "$env:SCP_SCHEDULER_ADMIN_TOKEN_FILE = $AdminTokenFile" in supervisor


def test_supervisor_recovers_external_ollama_with_budget():
    root = Path(__file__).resolve().parents[1]
    supervisor = (root / "scripts" / "ops" / "scp_247_supervisor.ps1").read_text(encoding="utf-8")
    assert "$ollamaHealthy = $DryRun -or (Test-HttpHealthy ($OllamaBaseUrl + '/api/tags'))" in supervisor
    assert "'OLLAMA_RECOVERED'" in supervisor
    assert "'OLLAMA_RECOVERY_FAILED'" in supervisor
    assert "'external_dependency_restart_budget_exhausted'" in supervisor
