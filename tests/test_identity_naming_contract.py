from pathlib import Path

from scp import __version__
from scp.api_server import app, health
from scp.api_server_parts.helpers import AskResponse
from scp.core.release_identity import (
    CANONICAL_MODEL_ID,
    DOMAIN_EXPERT_ENSEMBLE_TERM,
    LEGACY_MODEL_IDS,
    LEGACY_PROTOCOLS,
    RELEASE_LABEL,
    RELEASE_VERSION,
    model_id_candidates,
    public_release_metadata,
)
from scp.runtime.slm_base import BaseDomainExpert, BaseSLM, DomainExpertResponse, SLMResponse

ROOT = Path(__file__).resolve().parents[1]


def test_python_release_identity_is_single_source():
    assert __version__ == RELEASE_VERSION == "14.0.0"
    assert RELEASE_LABEL == f"SCP {RELEASE_VERSION}"
    assert CANONICAL_MODEL_ID == "scp-14.0.0"
    assert model_id_candidates() == (CANONICAL_MODEL_ID, *LEGACY_MODEL_IDS)
    metadata = public_release_metadata()
    assert metadata["release"] == RELEASE_LABEL
    assert metadata["expert_term"] == "Domain Expert"
    assert metadata["ensemble_term"] == DOMAIN_EXPERT_ENSEMBLE_TERM
    assert metadata["legacy_protocols"] == list(LEGACY_PROTOCOLS)


def test_domain_expert_aliases_preserve_old_runtime_classes():
    assert BaseDomainExpert is BaseSLM
    assert DomainExpertResponse is SLMResponse


def test_ask_response_populates_canonical_expert_fields_from_legacy_callers():
    trace = [{"domain": "math", "slm_name": "MathSLM", "answer": "4"}]
    response = AskResponse(
        verdict="PASS",
        final_answer="4",
        confidence=0.99,
        domain="math",
        elapsed_ms=1.0,
        session_id="identity-test",
        slm_trace=trace,
        slm_responses=trace,
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()
    assert payload["expert_trace"] == trace
    assert payload["expert_responses"] == trace
    assert payload["expert_ensemble"] == DOMAIN_EXPERT_ENSEMBLE_TERM
    assert payload["slm_trace"] == trace


def test_ask_response_does_not_overwrite_explicit_canonical_fields():
    legacy = [{"domain": "math", "answer": "legacy"}]
    canonical = [{"domain": "math", "answer": "canonical"}]
    response = AskResponse(
        verdict="PASS",
        final_answer="4",
        confidence=0.99,
        domain="math",
        elapsed_ms=1.0,
        session_id="identity-test-explicit",
        slm_trace=legacy,
        expert_trace=canonical,
        expert_ensemble="Custom Ensemble",
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()
    assert payload["expert_trace"] == canonical
    assert payload["expert_ensemble"] == "Custom Ensemble"
    assert payload["slm_trace"] == legacy


def test_fastapi_identity_and_minimal_health_contract():
    assert app.title == "SCP 14.0.0 - Self-Correcting Pipeline API"
    assert app.version == RELEASE_VERSION
    assert DOMAIN_EXPERT_ENSEMBLE_TERM in app.description
    payload = __import__("asyncio").run(health())
    assert payload["status"] == "ok"
    assert payload["version"] == RELEASE_VERSION
    assert payload["release"]["model_id"] == CANONICAL_MODEL_ID
    assert payload["release"]["legacy_protocols"] == list(LEGACY_PROTOCOLS)


def test_dashboard_identity_contract():
    version_ts = (ROOT / "dashboard" / "src" / "lib" / "audit-data" / "version.ts").read_text(encoding="utf-8")
    status_ts = (ROOT / "dashboard" / "src" / "app" / "api" / "scp" / "status" / "route.ts").read_text(encoding="utf-8")
    panel_ts = (ROOT / "dashboard" / "src" / "components" / "dashboard" / "scp-control-panel.tsx").read_text(encoding="utf-8")
    health_proxy_ts = (ROOT / "dashboard" / "src" / "app" / "api" / "scp" / "health" / "route.ts").read_text(encoding="utf-8")
    assert 'SCP_RELEASE_VERSION = "14.0.0"' in version_ts
    assert 'SCP_RELEASE_LABEL = `SCP ${SCP_RELEASE_VERSION}`' in version_ts
    assert "SCP_CANONICAL_MODEL_ID" in status_ts
    assert "modelId: SCP_CANONICAL_MODEL_ID" in status_ts
    assert "expertTerm: DOMAIN_EXPERT_ENSEMBLE_TERM" in status_ts
    assert "auditRound: CURRENT_ROUND" in status_ts
    assert "historicalEvidenceRound: 9" in status_ts
    assert "Autofix generation 4 (audit R9)" in status_ts
    assert '127.0.0.1:8002' in status_ts
    assert "status?.audit.auditRound" in panel_ts
    assert "CURRENT_ROUND" in panel_ts
    assert "status?.audit.round" not in panel_ts
    assert "port 8000" not in panel_ts
    assert "127.0.0.1:8000" not in panel_ts
    assert '127.0.0.1:8002' in health_proxy_ts
    assert 'SCP_PORT=8002 python -m scp' in health_proxy_ts


def test_openai_model_identity_contract():
    source = (ROOT / "scp" / "api" / "routes" / "openai_compat.py").read_text(encoding="utf-8")
    assert "CANONICAL_MODEL_ID" in source
    assert "model_id_candidates" in source
    assert '"deprecated": index != 0' in source


def test_legacy_naming_note_is_replaced_by_canonical_note():
    assert not (ROOT / "scp" / "runtime" / "SLM_NAMING_NOTE.md").exists()
    note = (ROOT / "scp" / "runtime" / "DOMAIN_EXPERT_NAMING.md").read_text(encoding="utf-8")
    assert "Domain Expert" in note
    assert "compatibility" in note.lower()


def test_minimal_health_note_is_utf8_and_user_visible_contract_is_clean():
    payload = __import__("asyncio").run(health())
    assert payload["note"] == "minimal health — use /health/detailed for full status"
    assert not any(marker in payload["note"] for marker in ("Ã", "Â", "Ä", "Ă", "â€", "�"))


def test_cli_docstring_matches_canonical_default_port():
    # [Fix R5] Port unification: 8002 is now canonical across all components
    # (supervisor, dashboard, CI, Dockerfile, Python entry point).
    # Running 'python -m scp' without a port now starts on 8002, making it
    # visible to the dashboard which proxies to 8002.
    source = (ROOT / "scp" / "__main__.py").read_text(encoding="utf-8")
    assert "Defaults to port 8002" in source
    assert "Defaults to port 8000" not in source
