import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scp.epistemic import EvidenceIntegrityError, EvidenceStore
from scp.epistemic.evidence_store import _IMMUTABLE_FIELDS, derive_repo_identity_key

# ==============================================================================
# T06 - EVIDENCE STORE (26-P0.05): immutable core, content dedupe, occurrence
# preservation, restart persistence, tamper detection, orphan reconciliation,
# missing-blob fail-closed.
# ==============================================================================


def _store(tmp_path):
    return EvidenceStore(tmp_path / "epistemic.sqlite3", tmp_path / "objects")


def _observe(store, content=b"observed-payload", **overrides):
    kwargs = dict(
        kind="RUNTIME_OBSERVATION",
        content=content,
        collector_id="test-collector",
        collector_version="1.0",
    )
    kwargs.update(overrides)
    return store.observe(**kwargs)


def test_same_content_twice_same_blob_two_occurrences(tmp_path):
    store = _store(tmp_path)
    first = _observe(store)
    second = _observe(store, metadata={"fetch": "second"})

    assert first["evidence_id"] != second["evidence_id"], "occurrence identity must never be deduped"
    assert first["content_hash"] == second["content_hash"], "content identity must match"
    blobs = store.db.query("SELECT COUNT(*) AS n FROM content_blobs")
    assert blobs[0]["n"] == 1, "content blob must be stored exactly once"
    assert store.read_content(first["evidence_id"]) == b"observed-payload"
    assert store.read_content(second["evidence_id"]) == b"observed-payload"


def test_evidence_table_is_machine_immutable(tmp_path):
    store = _store(tmp_path)
    record = _observe(store)
    with pytest.raises(Exception) as exc_info:
        store.db.execute(
            "UPDATE evidence SET source_id='tampered' WHERE evidence_id=?", (record["evidence_id"],)
        )
    assert "immutable" in str(exc_info.value), "the immutability trigger must abort raw UPDATEs"


def test_restart_persistence_and_tamper_detection(tmp_path):
    db_path = tmp_path / "epistemic.sqlite3"
    objects = tmp_path / "objects"
    store = EvidenceStore(db_path, objects)
    record = _observe(store, content=b"durable-bytes", source_id="src_1")
    store.db.close()

    reopened = EvidenceStore(db_path, objects)
    assert reopened.read_content(record["evidence_id"]) == b"durable-bytes"

    # Tamper with the payload on disk -> fail-closed, never returned as valid.
    blob = objects / record["content_ref"]
    blob.write_bytes(b"tampered-bytes")
    with pytest.raises(EvidenceIntegrityError, match="hash mismatch"):
        reopened.get(record["evidence_id"])

    # Missing blob (C4) -> fail-closed with MISSING state, metadata still durable.
    blob.unlink()
    with pytest.raises(EvidenceIntegrityError, match="MISSING"):
        reopened.get(record["evidence_id"])
    row = reopened.db.query(
        "SELECT source_id, kind FROM evidence WHERE evidence_id=?", (record["evidence_id"],)
    )
    assert row and row[0]["source_id"] == "src_1"


def test_supersede_never_rewrites_history(tmp_path):
    store = _store(tmp_path)
    old = _observe(store, content=b"old-value")
    new = store.supersede(
        old["evidence_id"],
        kind="RUNTIME_OBSERVATION",
        content=b"corrected-value",
        collector_id="test-collector",
        collector_version="1.1",
    )
    assert old["evidence_id"] != new["evidence_id"]
    links = store.db.query(
        "SELECT relation FROM evidence_links WHERE parent_evidence_id=? AND child_evidence_id=?",
        (old["evidence_id"], new["evidence_id"]),
    )
    assert links and links[0]["relation"] == "SUPERSEDES"
    assert store.read_content(old["evidence_id"]) == b"old-value", "history must survive the correction"


def test_crash_rollback_leaves_orphan_blob_and_reconciles(tmp_path, monkeypatch):
    """C2/C3: DB transaction rolls back after the blob was renamed -> the blob
    becomes an orphan that the scanner must find (never silently trusted)."""
    from scp.contracts import ids as ids_module
    from scp.epistemic import evidence_store as es_module

    store = _store(tmp_path)
    fixed_id = "ev_" + "0" * 24
    monkeypatch.setattr(es_module, "new_id", lambda prefix: fixed_id)

    _observe(store, content=b"forced-id-blob")  # consumes the fixed id
    with pytest.raises(Exception):
        _observe(store, content=b"second-occurrence-same-id")  # PK conflict -> rollback

    count = store.db.query("SELECT COUNT(*) AS n FROM evidence")[0]["n"]
    assert count == 1, "failed occurrence must not leave a half-written evidence row"
    orphans = store.scan_orphans()
    assert len(orphans) == 1, f"renamed-but-unreferenced blob must be reported as orphan: {orphans}"


def test_purge_keeps_metadata_and_records_retention_event(tmp_path):
    store = _store(tmp_path)
    record = _observe(store, content=b"purge-me")
    event_id = store.purge_payload(record["evidence_id"], reason="raw expired", policy="raw_7d")

    assert event_id.startswith("ret_")
    with pytest.raises(EvidenceIntegrityError, match="PURGED"):
        store.get(record["evidence_id"])
    events = store.db.query("SELECT reason, policy FROM retention_events WHERE retention_event_id=?", (event_id,))
    assert events and events[0]["reason"] == "raw expired"
    row = store.db.query("SELECT kind, content_hash FROM evidence WHERE evidence_id=?", (record["evidence_id"],))
    assert row, "metadata + hash must stay durable after payload purge"


def test_model_response_kind_is_accepted_and_labeled(tmp_path):
    store = _store(tmp_path)
    record = _observe(store, kind="MODEL_RESPONSE", content=b"model said X")
    assert record["kind"] == "MODEL_RESPONSE"
    # Semantic note enforced by docs/tests: this proves "model said X", never "X is true".
    with pytest.raises(ValueError):
        _observe(store, kind="DIVINE_TRUTH", content=b"nope")


# ------------------------------------------------------------------------------
# M5: append-only DELETE enforcement on every epistemic table.
# ------------------------------------------------------------------------------


def test_epistemic_tables_reject_delete(tmp_path):
    store = _store(tmp_path)
    parent = _observe(store, content=b"parent-payload")
    child = _observe(store, content=b"child-payload")
    store.link(parent["evidence_id"], child["evidence_id"], "SUPPORTS")

    with pytest.raises(Exception, match="append-only"):
        store.db.execute("DELETE FROM evidence WHERE evidence_id=?", (parent["evidence_id"],))
    with pytest.raises(Exception, match="append-only"):
        store.db.execute(
            "DELETE FROM evidence_links WHERE parent_evidence_id=?", (parent["evidence_id"],)
        )
    with pytest.raises(Exception, match="append-only"):
        store.db.execute("DELETE FROM content_blobs WHERE content_hash=?", (child["content_hash"],))

    # Nothing was actually removed.
    assert store.db.query("SELECT COUNT(*) AS n FROM evidence")[0]["n"] == 2
    assert store.db.query("SELECT COUNT(*) AS n FROM evidence_links")[0]["n"] == 1
    assert store.db.query("SELECT COUNT(*) AS n FROM content_blobs")[0]["n"] == 2


def test_lifecycle_tables_stay_mutable(tmp_path):
    store = _store(tmp_path)
    record = _observe(store, content=b"purge-me")
    event_id = store.purge_payload(record["evidence_id"], reason="raw expired", policy="raw_7d")

    # evidence_payload_state + retention_events are lifecycle tables: mutable
    # by design (only they are excluded from the append-only triggers).
    store.db.execute(
        "UPDATE evidence_payload_state SET payload_state='MISSING' WHERE evidence_id=?",
        (record["evidence_id"],),
    )
    store.db.execute("DELETE FROM retention_events WHERE retention_event_id=?", (event_id,))
    store.db._conn.commit()
    assert store.db.query("SELECT COUNT(*) AS n FROM retention_events")[0]["n"] == 0


# ------------------------------------------------------------------------------
# M5: keyed record_hash (HMAC-SHA256) - defense-in-depth against raw-SQL
# tampering that recomputes the unkeyed hash.
# ------------------------------------------------------------------------------


def _drop_update_trigger(store):
    store.db.execute("DROP TRIGGER evidence_no_update")
    store.db._conn.commit()


def test_keyless_store_keeps_plain_sha256_record_hash(tmp_path):
    store = _store(tmp_path)
    record = _observe(store)
    assert record["record_hash"].startswith("sha256:"), "default store must stay backward compatible"
    assert store.verify_integrity(record["evidence_id"])["ok"]


def test_keyed_store_writes_hmac_record_hash(tmp_path):
    store = EvidenceStore(tmp_path / "epistemic.sqlite3", tmp_path / "objects", hmac_key="unit-test-key")
    record = _observe(store)
    assert record["record_hash"].startswith("hmac-sha256:")
    assert store.verify_integrity(record["evidence_id"])["ok"]


def test_env_key_enables_hmac_record_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("SCP_EVIDENCE_HMAC_KEY", "env-hmac-secret")
    store = _store(tmp_path)
    record = _observe(store)
    assert record["record_hash"].startswith("hmac-sha256:")
    monkeypatch.delenv("SCP_EVIDENCE_HMAC_KEY")


def test_hmac_keyed_store_detects_raw_sql_tamper(tmp_path):
    """The full attack: drop the trigger, edit metadata, keep going.
    With an HMAC key the attacker cannot recompute the hash, so
    verify_integrity() fails closed."""
    store = EvidenceStore(tmp_path / "epistemic.sqlite3", tmp_path / "objects", hmac_key="unit-test-key")
    record = _observe(store, source_id="original")
    _drop_update_trigger(store)
    store.db.execute(
        "UPDATE evidence SET source_id='tampered' WHERE evidence_id=?", (record["evidence_id"],)
    )
    store.db._conn.commit()
    verdict = store.verify_integrity(record["evidence_id"])
    assert not verdict["ok"], "edited metadata must fail the keyed integrity check"
    assert any("tampered" in err for err in verdict["errors"])


def test_plain_sha256_cannot_detect_recomputed_hash_contrast(tmp_path):
    """Contrast baseline (documents WHY the HMAC key exists): with the unkeyed
    sha256 scheme, the same attacker recomputes the hash over the edited row
    and the tampering is UNDETECTABLE. The keyed mode above closes exactly
    this gap."""
    store = _store(tmp_path)
    record = _observe(store, source_id="original")
    _drop_update_trigger(store)
    store.db.execute(
        "UPDATE evidence SET source_id='tampered' WHERE evidence_id=?", (record["evidence_id"],)
    )
    store.db._conn.commit()
    row = dict(store.db.query("SELECT * FROM evidence WHERE evidence_id=?", (record["evidence_id"],))[0])
    canonical = json.dumps(
        {f: row[f] for f in _IMMUTABLE_FIELDS}, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    from scp.contracts.ids import content_id

    store.db.execute(
        "UPDATE evidence SET record_hash=? WHERE evidence_id=?",
        (content_id(canonical), record["evidence_id"]),
    )
    store.db._conn.commit()
    assert store.verify_integrity(record["evidence_id"])["ok"], (
        "baseline: plain sha256 offers no protection against hash recomputation"
    )


def test_keyed_store_refuses_recomputed_unkeyed_record_hash(tmp_path):
    """Scheme dispatch is fail-closed: a raw-SQL actor who swaps the keyed hash
    for a freshly recomputed PLAIN sha256 must still be caught."""
    store = EvidenceStore(tmp_path / "epistemic.sqlite3", tmp_path / "objects", hmac_key="unit-test-key")
    record = _observe(store)
    canonical = json.dumps(
        {f: record[f] for f in _IMMUTABLE_FIELDS}, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    plain_rehash = "sha256:" + hashlib.sha256(canonical).hexdigest()

    _drop_update_trigger(store)
    store.db.execute(
        "UPDATE evidence SET record_hash=? WHERE evidence_id=?", (plain_rehash, record["evidence_id"])
    )
    store.db._conn.commit()
    verdict = store.verify_integrity(record["evidence_id"])
    assert not verdict["ok"], "unkeyed hash must be refused by a keyed store"
    assert any("unkeyed" in err for err in verdict["errors"])


def test_keyed_row_without_configured_key_fails_closed(tmp_path):
    db_path = tmp_path / "epistemic.sqlite3"
    store = EvidenceStore(db_path, tmp_path / "objects", hmac_key="unit-test-key")
    record = _observe(store)
    store.db.close()

    reopened = EvidenceStore(db_path, tmp_path / "objects")  # no key configured
    verdict = reopened.verify_integrity(record["evidence_id"])
    assert not verdict["ok"], "keyed record must not validate without the key"
    assert any("no HMAC key is configured" in err for err in verdict["errors"])


def test_wrong_hmac_key_fails_closed(tmp_path):
    db_path = tmp_path / "epistemic.sqlite3"
    store = EvidenceStore(db_path, tmp_path / "objects", hmac_key="key-A")
    record = _observe(store)
    store.db.close()

    reopened = EvidenceStore(db_path, tmp_path / "objects", hmac_key="key-B")
    verdict = reopened.verify_integrity(record["evidence_id"])
    assert not verdict["ok"], "a different key must not validate someone else's records"


def test_derive_repo_identity_key_is_deterministic_and_not_empty(tmp_path):
    import shutil
    import tempfile

    key_a = derive_repo_identity_key(ROOT)
    key_b = derive_repo_identity_key(ROOT)
    assert key_a == key_b and key_a.startswith("sha256:")
    # A non-repo path falls back to the resolved path identity -> different key.
    outside = Path(tempfile.mkdtemp(prefix="scp-hmac-key-identity-"))
    try:
        assert derive_repo_identity_key(outside) != key_a
    finally:
        shutil.rmtree(outside, ignore_errors=True)
