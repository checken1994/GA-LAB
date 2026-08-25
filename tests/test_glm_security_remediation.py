from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scp.autofix.llm_fix import _validate_openrouter_base_url
from scp.autofix.realtime_verifier import _safe_exec_callable
from scp.core.knowledge_io import build_select_query
from scp.history.migration import MigrationConfig, _table_counts
from scp.runtime.safe_math import safe_eval_arithmetic
from scp.security.cisa_kev import _open_cisa_feed


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1"),
        ("https://api.openrouter.ai/api/v1/", "https://api.openrouter.ai/api/v1"),
        ("http://localhost:8002/v1", "http://localhost:8002/v1"),
        ("http://127.0.0.1:8002/v1", "http://127.0.0.1:8002/v1"),
    ],
)
def test_openrouter_base_url_allowlist(url: str, expected: str) -> None:
    assert _validate_openrouter_base_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://openrouter.ai/api/v1",
        "https://attacker.example/api/v1",
        "file:///etc/passwd",
        "https://user:pass@openrouter.ai/api/v1",
        "https://openrouter.ai/api/v1?next=https://attacker.example",
        "https://openrouter.ai:8443/api/v1",
        "https://openrouter.ai/api/v1#fragment",
        "https://openrouter.ai",
    ],
)
def test_openrouter_base_url_rejects_unsafe_values(url: str) -> None:
    with pytest.raises(ValueError):
        _validate_openrouter_base_url(url)


def test_cisa_feed_allows_fixed_https_hosts_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        seen.append(f"{getattr(request, 'full_url', '')}|{timeout}")
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with _open_cisa_feed("https://raw.githubusercontent.com/cisagov/kev-data/main/feed.json"):
        pass
    assert seen == ["https://raw.githubusercontent.com/cisagov/kev-data/main/feed.json|30"]


@pytest.mark.parametrize(
    "url",
    [
        "http://raw.githubusercontent.com/cisagov/kev-data/main/feed.json",
        "https://evil.example/cisa.json",
        "file:///tmp/cisa.json",
        "https://raw.githubusercontent.com@evil.example/cisa.json",
        "https://www.cisa.gov/feed.json?redirect=evil",
        "https://raw.githubusercontent.com/not-cisagov/feed.json",
    ],
)
def test_cisa_feed_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        _open_cisa_feed(url)


def test_safe_math_preserves_legacy_xor_and_rejects_code() -> None:
    assert safe_eval_arithmetic("7 ^ 5") == 2.0
    assert safe_eval_arithmetic("(2 + 3) * 4 / 2") == 10.0
    with pytest.raises((ValueError, SyntaxError)):
        safe_eval_arithmetic("__import__('os').system('echo bad')")
    with pytest.raises((ValueError, SyntaxError)):
        safe_eval_arithmetic("10 ** 101")


def test_restricted_exec_allows_function_and_rejects_imports_and_dunders() -> None:
    source = "def check(value):\n    return str(value)"
    function = _safe_exec_callable(source, "check", 42)
    assert function[1] is None
    assert function[0] == "42"

    rejected_import = "def check(value):\n    import os\n    return value"
    result, error = _safe_exec_callable(rejected_import, "check", 42)
    assert result is None
    assert isinstance(error, ValueError)

    rejected_dunder = "def check(value):\n    return value.__class__"
    result, error = _safe_exec_callable(rejected_dunder, "check", 42)
    assert result is None
    assert isinstance(error, ValueError)


def test_knowledge_query_requires_bound_placeholder_predicate() -> None:
    assert build_select_query("items", ["id", "name"], "id = ?") == (
        'SELECT "id", "name" FROM "items" WHERE id = ?'
    )
    with pytest.raises(ValueError):
        build_select_query("items", ["id"], "id = 1 OR 1 = 1")
    with pytest.raises(ValueError):
        build_select_query("items; DROP TABLE users", ["id"])


def test_migration_table_counts_accepts_safe_name_and_rejects_quoted_name(tmp_path: Path) -> None:
    safe_db = tmp_path / "safe.sqlite"
    with sqlite3.connect(safe_db) as connection:
        connection.execute("CREATE TABLE experiences (id INTEGER)")
        connection.executemany("INSERT INTO experiences VALUES (?)", [(1,), (2,)])
    assert _table_counts(safe_db, MigrationConfig()) == {"experiences": 2}

    unsafe_db = tmp_path / "unsafe.sqlite"
    with sqlite3.connect(unsafe_db) as connection:
        connection.execute('CREATE TABLE "bad""name" (id INTEGER)')
    with pytest.raises(ValueError):
        _table_counts(unsafe_db, MigrationConfig())
