import pytest
from scp.audit_engine.models import OracleVerdict, EvidenceRecord, AuditChallenge, EvidenceBundle, PromotionDecision
from scp.audit_engine.contract_adapter import ContractAdapter
from scp.audit_engine.snapshot import SnapshotAuthority
from scp.audit_engine.oracle import IndependentOracle
from scp.audit_engine.recorder import JournalRecorder
from scp.audit_engine.gate import PromotionGate

def test_contract_adapter():
    # 1. Normal
    adapter = ContractAdapter("my contract")
    ch = adapter.generate_challenge("c1", "prof1")
    assert ch.challenge_id == "c1"
    assert ch.required_profile == "prof1"
    
    # 2. Tamper / Fail closed
    assert adapter.verify_integrity(adapter.get_canonical_hash()) == True
    assert adapter.verify_integrity("wrong_hash") == False
    
    # 3. Mutation-test adapter
    adapter.tamper()
    assert adapter.verify_integrity(adapter.get_canonical_hash()) == False

    with pytest.raises(ValueError):
        ContractAdapter("")

def test_snapshot_authority():
    # Immutable vs mutable boundary
    sa = SnapshotAuthority({"f1.txt": "content1"})
    overlay = sa.create_execution_overlay()
    
    assert overlay.read_file("f1.txt") == "content1"
    overlay.write_file("f1.txt", "content2")
    
    # Immutable is unchanged
    immut = sa.get_immutable_snapshot()
    assert immut.get_file("f1.txt") == "content1"
    # Mutable overlay reflects changes
    assert overlay.read_file("f1.txt") == "content2"
    
    # Tamper test
    assert sa.verify_integrity() == True
    sa.tamper()
    assert sa.verify_integrity() == False

def test_independent_oracle():
    oracle = IndependentOracle()
    
    # Trace ok => NOT_FALSIFIED
    ev1 = oracle.evaluate("some trace data", "c1", "hash_abc")
    assert ev1.verdict == OracleVerdict.NOT_FALSIFIED
    
    # Trace fail => FALSIFIED
    ev2 = oracle.evaluate("some trace FAIL ...", "c1", "hash_abc")
    assert ev2.verdict == OracleVerdict.FALSIFIED
    
    # Trace invalid => INVALID_TEST_SETUP
    ev3 = oracle.evaluate("INVALID config", "c1", "hash_abc")
    assert ev3.verdict == OracleVerdict.INVALID_TEST_SETUP
    
    # No trace => OBSERVABILITY_INSUFFICIENT
    ev4 = oracle.evaluate("", "c1", "hash_abc")
    assert ev4.verdict == OracleVerdict.OBSERVABILITY_INSUFFICIENT
    
    # Tampered => CONTAMINATED
    oracle.tamper()
    ev5 = oracle.evaluate("perfect trace", "c1", "hash_abc")
    assert ev5.verdict == OracleVerdict.CONTAMINATED

def test_journal_recorder():
    recorder = JournalRecorder()
    ev = EvidenceRecord("r1", OracleVerdict.NOT_FALSIFIED, "c1", "cov1")
    recorder.record(ev)
    assert len(recorder.get_journal()) == 1
    
    # Missing observer coverage
    ev_bad = EvidenceRecord("r2", OracleVerdict.NOT_FALSIFIED, "c1", "")
    with pytest.raises(ValueError):
        recorder.record(ev_bad)

def test_promotion_gate():
    gate = PromotionGate()
    ch = AuditChallenge("c1", "prof1", "hash1")
    
    # Valid bundle requires multiple verifications
    ev1 = EvidenceRecord("r1", OracleVerdict.NOT_FALSIFIED, "c1", "cov1")
    ev2 = EvidenceRecord("r2", OracleVerdict.NOT_FALSIFIED, "c1", "cov2")
    bundle = EvidenceBundle("b1", ch, [ev1, ev2])
    
    dec = gate.evaluate_bundle(bundle)
    assert dec.promoted is True
    
    # Single record => False
    b2 = EvidenceBundle("b2", ch, [ev1])
    dec2 = gate.evaluate_bundle(b2)
    assert dec2.promoted is False
    
    # Has a non NOT_FALSIFIED record => False
    ev3 = EvidenceRecord("r3", OracleVerdict.FALSIFIED, "c1", "cov3")
    b3 = EvidenceBundle("b3", ch, [ev1, ev3])
    dec3 = gate.evaluate_bundle(b3)
    assert dec3.promoted is False
    
    # Mismatched challenge ID => False
    ev4 = EvidenceRecord("r4", OracleVerdict.NOT_FALSIFIED, "c2", "cov4")
    b4 = EvidenceBundle("b4", ch, [ev1, ev4])
    dec4 = gate.evaluate_bundle(b4)
    assert dec4.promoted is False
    assert "does not belong to challenge" in dec4.reason

    # Tampered gate => False (Fail closed)
    gate.tamper()
    dec5 = gate.evaluate_bundle(bundle)
    assert dec5.promoted is False
    assert dec5.reason == "Gate is contaminated (Fail-closed)."
