"""Hermetic tests for the Free API Catalog (public-apis warehouse)."""
from __future__ import annotations

import json

import pytest

from scp.data_sources.free_api_catalog import FreeAPICatalog, parse_catalog_md

# Both header shapes seen in the real README + a sponsor table that must be
# skipped + one malformed row that must not crash the parser.
SAMPLE_MD = """\
### APILayer APIs
| API | Description | Call this API |
|:---|:---|:---|
| [IPstack](https://ipstack.com/) | Locate Visitors by IP | [button](https://x.example) |

### Blockchain
| API | Description | Auth | HTTPS | CORS |
|---|:---|:---|:---|:---|
| [Bitquery](https://graphql.bitquery.io/ide) | Onchain GraphQL APIs | `apiKey` | Yes | Yes |
| [Chainlink](https://chain.link/) | Hybrid smart contracts | No | Yes | Unknown |

### Books
API | Description | Auth | HTTPS | CORS |
|:---|:---|:---|:---|:---|
| [A Bíblia Digital](https://www.abibliadigital.com.br/en) | Digital Bible | `apiKey` | Yes | No |
| [Google Books](https://developers.google.com/books) | Books search | `apiKey` | Yes | Yes |
not a table row
"""


def test_parse_accepts_both_header_shapes_and_skips_sponsor():
    entries = parse_catalog_md(SAMPLE_MD)
    names = {(e["category"], e["name"]) for e in entries}
    assert ("Blockchain", "Bitquery") in names
    assert ("Blockchain", "Chainlink") in names
    assert ("Books", "A Bíblia Digital") in names
    assert ("Books", "Google Books") in names
    assert all(cat not in {"APILayer APIs"} for _, cat in names)
    assert not any(e["name"] == "IPstack" for e in entries)


def test_parse_fields():
    entries = parse_catalog_md(SAMPLE_MD)
    bitquery = next(e for e in entries if e["name"] == "Bitquery")
    assert bitquery["auth"] == "apiKey"
    assert bitquery["https"] == "Yes"
    assert bitquery["cors"] == "Yes"
    assert bitquery["description"] == "Onchain GraphQL APIs"
    assert bitquery["url"] == "https://graphql.bitquery.io/ide"


def test_search_filters_by_query_category_auth(tmp_path):
    catalog = FreeAPICatalog(data_dir=str(tmp_path))
    catalog._entries = parse_catalog_md(SAMPLE_MD)
    assert len(catalog.search(query="graphql")) == 1
    assert len(catalog.search(category="Books")) == 2
    no_key = catalog.search(auth="No")
    assert {e["name"] for e in no_key} == {"Chainlink"}
    assert catalog.search(query="nonexistent-token") == []


def test_cache_roundtrip_and_refresh(tmp_path):
    catalog = FreeAPICatalog(data_dir=str(tmp_path), transport=lambda url: SAMPLE_MD.encode("utf-8"))
    result = catalog.refresh(force=True)
    assert result["ok"] is True and result["served"] == "network"
    assert result["count"] == 4
    assert catalog.cache_path.exists()
    payload = json.loads(catalog.cache_path.read_text(encoding="utf-8"))
    assert payload["count"] == 4 and payload["raw_sha256"].startswith("sha256:")
    # New instance reads purely from cache (no transport).
    cold = FreeAPICatalog(data_dir=str(tmp_path))
    assert len(cold.entries()) == 4
    assert cold.status()["cached"] is True


def test_refresh_fail_closed_serves_cache(tmp_path):
    def broken_transport(url: str) -> bytes:
        raise ConnectionError("network down")

    catalog = FreeAPICatalog(data_dir=str(tmp_path), transport=broken_transport)
    result = catalog.refresh(force=True)
    assert result["ok"] is False and result["served"] == "none"
    # After a successful cache exists, a failing refresh still serves entries.
    catalog2 = FreeAPICatalog(data_dir=str(tmp_path), transport=lambda url: SAMPLE_MD.encode("utf-8"))
    catalog2.refresh(force=True)
    catalog2._transport = broken_transport
    result2 = catalog2.refresh(force=True)
    assert result2["ok"] is False and result2["served"] == "cache"
    assert len(catalog2.entries()) == 4


def test_http_get_rejects_non_allowlisted_host():
    from scp.data_sources.free_api_catalog import _egress_disabled  # noqa: F401

    with pytest.raises(ValueError):
        FreeAPICatalog._http_get("https://evil.example.com/README.md")
    with pytest.raises(ValueError):
        FreeAPICatalog._http_get("http://raw.githubusercontent.com/x")
