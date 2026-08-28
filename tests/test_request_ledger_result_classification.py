from scp.core.request_run_ledger import RequestRunLedger


def test_success_dict_without_verdict_is_success():
    assert RequestRunLedger.classify_result({"status": "ok", "value": 1}) == "SUCCESS"
    assert RequestRunLedger.classify_result({"success": True, "items": []}) == "SUCCESS"
    assert RequestRunLedger.classify_result({"ok": True, "data": {}}) == "SUCCESS"


def test_policy_false_dict_is_rejected_but_error_dict_is_internal_failure():
    assert RequestRunLedger.classify_result({"success": False, "allowed": False, "reason": "denied"}) == "REJECTED"
    assert RequestRunLedger.classify_result({"success": False, "error": "unexpected"}) == "INTERNAL_FAILED"
    assert RequestRunLedger.classify_result({"error": "unexpected"}) == "INTERNAL_FAILED"


def test_explicit_verdicts_keep_existing_semantics():
    assert RequestRunLedger.classify_result({"verdict": "PASS"}) == "SUCCESS"
    assert RequestRunLedger.classify_result({"verdict": "UNKNOWN"}) == "UNKNOWN"
    assert RequestRunLedger.classify_result({"verdict": "FAIL"}) == "REJECTED"
    assert RequestRunLedger.classify_result({"run_status": "TIMEOUT"}) == "TIMEOUT"
