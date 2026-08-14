from pathlib import Path


def test_electron_allows_only_local_dashboard_media_permission():
    root = Path(__file__).resolve().parents[1]
    source = (root / "desktop" / "main.cjs").read_text(encoding="utf-8")
    assert "setPermissionRequestHandler" in source
    assert "permission === 'media'" in source
    assert "url.port === '3000'" in source
    assert "callback(_webContents, _permission, callback) => callback(false)" not in source


def test_desktop_control_tabs_have_real_actions_and_error_text():
    root = Path(__file__).resolve().parents[1]
    source = (root / "dashboard" / "src" / "components" / "dashboard" / "scp-overview.tsx").read_text(encoding="utf-8")
    assert 'data-testid="system-tab"' in source
    assert 'data-testid="fix-tab"' in source
    assert 'fetch("/api/scp/loop/trigger"' in source
    assert "response.status" in source
    assert "setFixing" in source
    assert "setActiveTab(\"system\")" in source
    assert "setActiveTab(\"fix\")" in source
