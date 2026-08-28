from __future__ import annotations

import json

from scp.security.escalation import EscalationManager


def test_timeout_terminalizes_and_cleans_state(tmp_path, monkeypatch) -> None:
    manager = EscalationManager(data_dir=str(tmp_path))
    threat = {"id": "threat-timeout", "severity": "high", "type": "exploit_attempt"}
    manager.execute_defensive_playbook = lambda _threat: {"enforcement_performed": False}  # type: ignore[method-assign]

    manager.on_threat_detected(threat)
    assert manager.escalation_status()["armed_count"] == 1
    assert manager.escalation_status()["timers_count"] == 1
    manager.on_timeout(threat)

    status = manager.escalation_status()
    assert status["active_count"] == 0
    assert status["armed_count"] == 0
    assert status["timers_count"] == 0
    assert manager.get_escalation_history()[-1]["action"] == "timeout"
    persisted = json.loads((tmp_path / "escalation_state.json").read_text(encoding="utf-8"))
    assert persisted["active"] == {}
    assert persisted["history"][-1]["action"] == "timeout"


def test_restart_restores_armed_deadline_and_timer(tmp_path) -> None:
    threat = {"id": "threat-restart", "severity": "high", "type": "exploit_attempt"}
    first = EscalationManager(data_dir=str(tmp_path))
    first.on_threat_detected(threat)
    first._timers["threat-restart"].cancel()

    restored = EscalationManager(data_dir=str(tmp_path))
    try:
        status = restored.escalation_status()
        assert status["active_count"] == 1
        assert status["armed_count"] == 1
        assert status["timers_count"] == 1
        assert restored._active["threat-restart"]["deadline_at"] > restored._now()
    finally:
        restored._timers.get("threat-restart").cancel()
