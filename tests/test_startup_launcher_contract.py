from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / "start-scp.bat").read_text(encoding="utf-8")


def test_manual_launcher_preflights_dashboard_dependency_and_build():
    assert 'dashboard\\node_modules\\next\\dist\\bin\\next' in LAUNCHER
    assert 'bun install --frozen-lockfile' in LAUNCHER
    assert 'start "SCP-Dashboard" cmd /k "cd /d %~dp0dashboard && bun run start"' in LAUNCHER
    assert 'bun run build' in LAUNCHER


def test_manual_launcher_treats_ollama_as_external_dependency():
    assert 'http://127.0.0.1:11434/api/tags' in LAUNCHER
    assert 'start "SCP-LLM-Bridge"' not in LAUNCHER
    assert 'mini-services\\llm-bridge\\node_modules' not in LAUNCHER
    assert 'Ollama:          http://127.0.0.1:11434/api/tags' in LAUNCHER
