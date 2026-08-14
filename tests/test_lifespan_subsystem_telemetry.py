from pathlib import Path


def test_lifespan_long_running_subsystems_are_heartbeat_bound():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scp" / "api" / "_lifespan.py").read_text(encoding="utf-8")
    assert "_wait_with_heartbeat" in source
    assert 'SubsystemTelemetry("deep_audit"' in source
    assert 'SubsystemTelemetry("attack_monitor"' in source
    assert '"deep_audit_stop"' in source
    assert '"attack_monitor_stop"' in source
    assert ', "IDLE")' in source
