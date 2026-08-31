from __future__ import annotations

import ast
import inspect

import pytest

from scp.autofix.scanners import hypothesis_scanner
from scp.core import knowledge_curation
from scp.knowledge import issue_parser


def test_hypothesis_scanner_builds_only_internal_strategy_specs() -> None:
    tree = ast.parse(
        "def target(name: str, count: int, enabled: bool):\n"
        "    return name, count, enabled\n"
    )
    node = tree.body[0]
    assert isinstance(node, ast.FunctionDef)

    assert hypothesis_scanner._build_strategy_specs(node) == (
        "st.text()",
        "st.integers()",
        "st.booleans()",
    )


def test_hypothesis_scanner_contains_no_eval_call() -> None:
    tree = ast.parse(inspect.getsource(hypothesis_scanner))
    eval_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "eval"
    ]
    assert eval_calls == []


def test_hypothesis_scanner_rejects_unknown_strategy_spec() -> None:
    with pytest.raises(ValueError, match="unsupported hypothesis strategy spec"):
        hypothesis_scanner._strategy_from_spec("st.from_regex('.*')", object())


@pytest.mark.parametrize(
    "url",
    [
        "http://export.arxiv.org/api/query?q=scp",
        "https://hn.algolia.com/api/v1/search?q=scp",
        "https://api.stackexchange.com/2.3/search/advanced?q=scp",
    ],
)
def test_scraper_url_guard_allows_declared_sources(url: str) -> None:
    knowledge_curation._validate_scraper_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://127.0.0.1/internal",
        "https://hn.algolia.com.evil.example/api",
        "https://attacker@hn.algolia.com/api",
        "https://hn.algolia.com:8443/api",
    ],
)
def test_scraper_url_guard_rejects_ssrf_shapes(url: str) -> None:
    with pytest.raises(ValueError):
        knowledge_curation._validate_scraper_url(url)


def test_scraper_redirects_are_revalidated() -> None:
    handler = knowledge_curation._AllowlistedRedirectHandler()
    with pytest.raises(ValueError, match="not allowlisted"):
        handler.redirect_request(
            req=None,
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="http://169.254.169.254/latest/meta-data/",
        )


def test_scraper_open_is_rate_limited_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    response = object()

    class FakeBucket:
        def acquire(self) -> None:
            calls.append("acquire")

    class FakeOpener:
        def open(self, request, *, timeout):  # noqa: ANN001, ANN201
            calls.append((request.full_url, timeout))
            return response

    monkeypatch.setattr(knowledge_curation, "_CURATED_BUCKET", FakeBucket())
    monkeypatch.setattr(knowledge_curation, "_SCRAPER_OPENER", FakeOpener())

    actual = knowledge_curation._open_scraper_url(
        "https://hn.algolia.com/api/v1/search?q=scp",
        timeout=7.5,
    )

    assert actual is response
    assert calls == [
        "acquire",
        ("https://hn.algolia.com/api/v1/search?q=scp", 7.5),
    ]


def test_issue_parser_sets_network_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        status_code = 503

    def fake_get(url: str, **kwargs: object) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(issue_parser.requests, "get", fake_get)

    assert issue_parser.parse_top_1_percent_issues() == 0
    assert captured["timeout"] == 15
    assert str(captured["url"]).startswith("https://api.github.com/")
