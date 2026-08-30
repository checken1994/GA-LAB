from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.yml").read_text(encoding="utf-8")
DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")
CONTAINER_README = (ROOT / "deploy" / "container" / "README.md").read_text(encoding="utf-8")


def test_api_image_is_non_root_and_has_healthcheck() -> None:
    assert "useradd --create-home --uid 10001" in DOCKERFILE
    assert "USER scp" in DOCKERFILE
    assert "HEALTHCHECK" in DOCKERFILE
    assert "127.0.0.1:8000:8000" in COMPOSE
    assert "cap_drop:" in COMPOSE
    assert "no-new-privileges:true" in COMPOSE


def test_build_context_excludes_private_and_runtime_artifacts() -> None:
    for pattern in (".env", "secrets/", "*.pem", "*.key", "**/*.sqlite", "**/*.jsonl"):
        assert pattern in DOCKERIGNORE
    assert "COPY scp ./scp" in DOCKERFILE
    assert "COPY ." not in DOCKERFILE


def test_scheduler_is_opt_in_and_observe_only() -> None:
    assert 'profiles: ["loop"]' in COMPOSE
    assert "SCP_AUTOFIX_MODE: observe" in COMPOSE
    assert "SCP_AUTOFIX_DETERMINISTIC_ONLY: \"1\"" in COMPOSE
    assert "docker compose -f compose.yml --profile loop up -d" in CONTAINER_README


def test_container_docs_do_not_embed_credentials_or_claim_production() -> None:
    forbidden = ("sk-", "Bearer ", "password=", "token=")
    for value in forbidden:
        assert value not in DOCKERFILE
        assert value not in COMPOSE
    assert "không phải bằng chứng SCP đã triển khai production hay VPS" in CONTAINER_README
