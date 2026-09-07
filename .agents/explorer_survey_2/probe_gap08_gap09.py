#!/usr/bin/env python3
"""
Adversarial Probe for GAP-08 and GAP-09
Exploit Mandate (FA-09) proof of vulnerability:
1. GAP-08: Capability token forgery without HMAC signature.
2. GAP-09: Hardcoded fallback secret used when SCP_CAPABILITY_SECRET is missing.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def test_gap08_forgery_vulnerability():
    print("\n--- Testing GAP-08: Token Forgery Without Cryptographic Signature ---")
    from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken
    
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "capability_state.json"
        cap_auth = CapabilityAuthority(state_file)
        
        # Attacker constructs a forged token without any signature or authority involvement
        forged_token = CapabilityToken(
            subject="hands:pc.write_file",
            epoch=0,
            token_id="unauthorized_attacker_id_999",
            issued_at=time.time(),
        )
        
        # Validate against the authority
        is_valid = cap_auth.validate(forged_token, required_subject="hands:pc.write_file")
        print(f"Attacker forged token: {forged_token}")
        print(f"cap_auth.validate(forged_token) result: {is_valid}")
        
        if is_valid is True:
            print(">>> [VULNERABILITY CONFIRMED - RED]: CapabilityAuthority accepted an unsigned, forged token!")
            return True
        else:
            print(">>> [REJECTED]: Forged token was rejected.")
            return False

def test_gap09_fallback_secret_vulnerability():
    print("\n--- Testing GAP-09: Hardcoded Fallback Secret When Env Var Unset ---")
    
    # Ensure environment does not have SCP_CAPABILITY_SECRET
    os.environ.pop("SCP_CAPABILITY_SECRET", None)
    
    # Attempt to import scp.core.capability_token
    import importlib
    import scp.core.capability_token as cap_mod
    importlib.reload(cap_mod)
    
    loaded_secret = getattr(cap_mod, "_SECRET", None)
    print(f"Loaded secret when SCP_CAPABILITY_SECRET is unset: {loaded_secret}")
    
    expected_vuln_secret = b"dev-secret-do-not-use-in-prod-12345"
    if loaded_secret == expected_vuln_secret:
        print(">>> [VULNERABILITY CONFIRMED - RED]: scp.core.capability_token used hardcoded dev-secret fallback!")
        return True
    else:
        print(f">>> [FAIL-CLOSED OR FIXED]: Secret was not fallback: {loaded_secret}")
        return False

if __name__ == "__main__":
    v1 = test_gap08_forgery_vulnerability()
    v2 = test_gap09_fallback_secret_vulnerability()
    print("\nSummary:")
    print(f"GAP-08 Unsigned Forgery Vulnerable: {v1}")
    print(f"GAP-09 Fallback Secret Vulnerable:   {v2}")
    if v1 and v2:
        print("\nBoth GAP-08 and GAP-09 vulnerabilities strictly confirmed via live terminal execution (FA-09 SATISFIED).")
        sys.exit(0)
    else:
        sys.exit(1)
