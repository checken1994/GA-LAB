from pathlib import Path
import json
import pytest
from scp.security.production_guard import enforce_production_safety
from scp.security.secret_loader import read_secret
ROOT = Path(__file__).resolve().parents[1]

def test_secret_file_precedence(monkeypatch, tmp_path):
    p = tmp_path / "s"
    p.write_text("file-value\n", encoding="utf-8")
    monkeypatch.setenv("TEST_INLINE", "inline-value")
    monkeypatch.setenv("TEST_FILE", str(p))
    assert read_secret("TEST_INLINE", "TEST_FILE") == "file-value"

def test_secret_inline_fallback(monkeypatch):
    monkeypatch.setenv("TEST_INLINE", "inline-value")
    monkeypatch.delenv("TEST_FILE", raising=False)
    assert read_secret("TEST_INLINE", "TEST_FILE") == "inline-value"

def test_secret_missing_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_FILE", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="TEST_FILE"):
        read_secret("TEST_INLINE", "TEST_FILE")

def test_production_guard_rejects_bypass(monkeypatch):
    monkeypatch.setenv("SCP_PRODUCTION_MODE", "1")
    monkeypatch.setenv("SCP_DEV_MODE", "1")
    with pytest.raises(RuntimeError, match="SCP_DEV_MODE"):
        enforce_production_safety()

def test_production_guard_inactive_without_mode(monkeypatch):
    monkeypatch.delenv("SCP_PRODUCTION_MODE", raising=False)
    monkeypatch.setenv("SCP_DEV_MODE", "1")
    enforce_production_safety()

def test_electron_contract():
    s = (ROOT / "desktop" / "main.cjs").read_text(encoding="utf-8")
    for marker in ("contextIsolation: true", "sandbox: true", "setPermissionRequestHandler", "setWindowOpenHandler", "SCP_SCHEDULER_ADMIN_TOKEN_FILE"):
        assert marker in s

def test_dashboard_tabs_contract():
    s = (ROOT / "dashboard" / "src" / "components" / "dashboard" / "scp-overview.tsx").read_text(encoding="utf-8")
    for marker in ("activeTab", "triggerControlledFix", "Chạy kiểm tra ngay", "Gửi yêu cầu sửa có kiểm soát"):
        assert marker in s

def test_trigger_route_contract():
    s = (ROOT / "dashboard" / "src" / "app" / "api" / "scp" / "loop" / "trigger" / "route.ts").read_text(encoding="utf-8")
    for marker in ("export async function POST", "SCP_SCHEDULER_ADMIN_TOKEN_FILE", "Authorization", "AbortSignal.timeout"):
        assert marker in s

def test_electron_csp_contract():
    s = (ROOT / "desktop" / "main.cjs").read_text(encoding="utf-8")
    for marker in ("PRODUCTION_CSP", "installDesktopCsp", "Content-Security-Policy", "script-src 'self'", "object-src 'none'"):
        assert marker in s


def test_packaged_backend_contract():
    main = (ROOT / "desktop" / "main.cjs").read_text(encoding="utf-8")
    manifest_path = ROOT / "desktop" / "runtime-manifest.json"
    build_script = ROOT / "desktop" / "build_runtime.ps1"
    desktop_package = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))
    runtime_filter = desktop_package["build"]["extraResources"][0]["filter"]
    assert "scp-backend.exe" in main
    assert "!data/**/*" in runtime_filter
    assert "!**/*.py" in runtime_filter
    assert manifest_path.exists()
    assert build_script.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact_policy"] == "generated-or-attached-release-asset"
    assert set(manifest["required_artifacts"]) == {
        "scp-backend.exe",
        "scp-llm-bridge.exe",
        "scp-loop-scheduler.exe",
        "scp-autofix-worker.exe",
    }
    runtime = ROOT / "desktop" / "runtime"
    onefile = runtime / "scp-backend.exe"
    onedir = runtime / "scp-backend" / "scp-backend.exe"
    # Source repos intentionally do not track the 245 MB Windows binary.
    # If a release bundle has staged it, enforce the no-source/no-live-data rule.
    if onefile.exists() or onedir.exists():
        if onedir.exists():
            assert not list((runtime / "scp-backend" / "_internal" / "scp").rglob("*.py"))
        else:
            assert not list(runtime.rglob("*.py"))
def test_bounded_startup_gate_contract():
    api = (ROOT / "scp" / "api_server.py").read_text(encoding="utf-8")
    for marker in ("SCP_STARTUP_SCAN_TIMEOUT_SEC", "asyncio.to_thread", "_startup_gate_task", "SCP_JUDGE_START_DELAY_SEC"):
        assert marker in api
