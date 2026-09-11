import pytest
import time
from scp.core.verifier_receipt import (
    VerifierReceipt,
    get_verifier_secret,
    MissingSecretError,
    canonical_receipt_bytes,
    InvalidReceiptSignatureError,
    sign_verifier_receipt,
    verify_verifier_receipt,
)

def test_get_verifier_secret_empty_bytes():
    with pytest.raises(MissingSecretError, match="Provided secret bytes must not be empty"):
        get_verifier_secret(b"")

def test_get_verifier_secret_empty_string():
    with pytest.raises(MissingSecretError, match="Provided secret string must not be empty"):
        get_verifier_secret("   ")

def test_canonical_receipt_bytes_dict_invalid_issued_at():
    receipt = {
        "task_id": "T-123",
        "verifier_id": "V-1",
        "verdict": "VERIFIED",
        "evidence_ref": "some-ref",
        "issued_at": "not-a-float"
    }
    with pytest.raises(InvalidReceiptSignatureError, match="Invalid issued_at timestamp in receipt"):
        canonical_receipt_bytes(receipt)

def test_canonical_receipt_bytes_obj_invalid_issued_at():
    receipt = VerifierReceipt(
        task_id="T-123",
        verifier_id="V-1",
        verdict="VERIFIED",
        evidence_ref="some-ref",
        issued_at="not-a-float"  # type: ignore
    )
    with pytest.raises(InvalidReceiptSignatureError, match="Invalid issued_at timestamp in receipt"):
        canonical_receipt_bytes(receipt)

def test_canonical_receipt_bytes_invalid_type():
    with pytest.raises(InvalidReceiptSignatureError, match="receipt must be a VerifierReceipt or dict"):
        canonical_receipt_bytes(["invalid", "type"])  # type: ignore

def test_sign_verifier_receipt_replace_issued_at():
    receipt = VerifierReceipt(
        task_id="T-123",
        verifier_id="V-1",
        verdict="VERIFIED",
        evidence_ref="some-ref",
        issued_at=0.0
    )
    signed = sign_verifier_receipt(receipt, secret="mysecret")
    assert signed.issued_at > 0.0

def test_sign_verifier_receipt_invalid_type():
    with pytest.raises(InvalidReceiptSignatureError, match="receipt must be a VerifierReceipt or dict"):
        sign_verifier_receipt(["invalid", "type"], secret="mysecret")  # type: ignore

def test_verify_verifier_receipt_none():
    with pytest.raises(InvalidReceiptSignatureError, match="Verifier receipt is missing or empty"):
        verify_verifier_receipt(None, secret="mysecret")  # type: ignore

def test_verify_verifier_receipt_invalid_type():
    with pytest.raises(InvalidReceiptSignatureError, match="Verifier receipt must be a VerifierReceipt or dict"):
        verify_verifier_receipt(["invalid", "type"], secret="mysecret")  # type: ignore

def test_verify_verifier_receipt_missing_task_id():
    receipt = {
        "verifier_id": "V-1",
        "verdict": "VERIFIED",
        "evidence_ref": "some-ref",
        "issued_at": time.time(),
        "signature": "dummy"
    }
    with pytest.raises(InvalidReceiptSignatureError, match="Verifier receipt missing task_id"):
        verify_verifier_receipt(receipt, secret="mysecret")

def test_verify_verifier_receipt_missing_verifier_id():
    receipt = {
        "task_id": "T-123",
        "verdict": "VERIFIED",
        "evidence_ref": "some-ref",
        "issued_at": time.time(),
        "signature": "dummy"
    }
    with pytest.raises(InvalidReceiptSignatureError, match="Verifier receipt missing verifier_id"):
        verify_verifier_receipt(receipt, secret="mysecret")

def test_verify_verifier_receipt_invalid_verdict():
    receipt = {
        "task_id": "T-123",
        "verifier_id": "V-1",
        "verdict": "FAILED",
        "evidence_ref": "some-ref",
        "issued_at": time.time(),
        "signature": "dummy"
    }
    with pytest.raises(InvalidReceiptSignatureError, match="Completion requires verifier verdict 'VERIFIED'"):
        verify_verifier_receipt(receipt, secret="mysecret")

def test_verify_verifier_receipt_missing_evidence_ref():
    receipt = {
        "task_id": "T-123",
        "verifier_id": "V-1",
        "verdict": "VERIFIED",
        "issued_at": time.time(),
        "signature": "dummy"
    }
    with pytest.raises(InvalidReceiptSignatureError, match="Verifier receipt missing evidence_ref"):
        verify_verifier_receipt(receipt, secret="mysecret")

def test_verify_verifier_receipt_invalid_issued_at():
    receipt = {
        "task_id": "T-123",
        "verifier_id": "V-1",
        "verdict": "VERIFIED",
        "evidence_ref": "some-ref",
        "issued_at": "not-a-float",
        "signature": "dummy"
    }
    with pytest.raises(InvalidReceiptSignatureError, match="Invalid timestamp in verifier receipt"):
        verify_verifier_receipt(receipt, secret="mysecret")


def test_get_verifier_secret_valid_bytes():
    assert get_verifier_secret(b'secret') == b'secret'
