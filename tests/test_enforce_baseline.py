from __future__ import annotations

import sys
from types import SimpleNamespace

from scripts import enforce_baseline


def test_baseline_uses_active_python_module_invocation(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(enforce_baseline.subprocess, "run", fake_run)

    assert enforce_baseline.main() == 0
    assert captured["command"][:3] == [sys.executable, "-m", "pytest"]
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"]["timeout"] == 900


def test_baseline_fails_closed_on_missing_pytest(monkeypatch) -> None:
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("pytest environment missing")

    monkeypatch.setattr(enforce_baseline.subprocess, "run", missing)

    assert enforce_baseline.main() == 2


def test_baseline_propagates_test_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        enforce_baseline.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stdout="one failed", stderr=""
        ),
    )

    assert enforce_baseline.main() == 1
