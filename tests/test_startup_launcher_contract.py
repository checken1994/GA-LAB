from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / "start-scp.bat").read_text(encoding="utf-8")


def test_manual_launcher_preflights_dashboard_dependency_and_build():
    assert 'dashboard\\node_modules\\next\\dist\\bin\\next' in LAUNCHER
    assert 'bun install --frozen-lockfile' in LAUNCHER
    assert 'start "SCP-Dashboard" cmd /k "cd /d %~dp0dashboard && set SCP_INTERNAL_URL=http://127.0.0.1:8002' in LAUNCHER
    assert '&& bun run start"' in LAUNCHER
    assert 'bun run build' in LAUNCHER


def test_manual_launcher_treats_ollama_as_external_dependency():
    assert 'http://127.0.0.1:11434/api/tags' in LAUNCHER
    assert 'start "SCP-LLM-Bridge"' not in LAUNCHER
    assert 'mini-services\\llm-bridge\\node_modules' not in LAUNCHER
    assert 'findstr ":11434 "' not in LAUNCHER
    assert 'set SCP_INTERNAL_URL=http://127.0.0.1:8002' in LAUNCHER
    assert 'set LOOP_SCHEDULER_URL=http://127.0.0.1:3030' in LAUNCHER
    assert 'set OLLAMA_HOST=http://127.0.0.1:11434' in LAUNCHER
    assert 'Ollama:          http://127.0.0.1:11434/api/tags' in LAUNCHER


def test_stop_launcher_never_kills_external_ollama_port():
    stop = (ROOT / "stop-scp.bat").read_text(encoding="utf-8")
    assert 'findstr ":11434 "' not in stop
    kill_lines = [line.lower() for line in stop.splitlines() if 'taskkill' in line.lower()]
    assert all('11434' not in line for line in kill_lines)
    assert 'taskkill' in stop.lower()
