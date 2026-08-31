import hmac
import hashlib
import json
import time
import base64
import os
import logging

logger = logging.getLogger(__name__)

_SECRET_STR = os.environ.get("SCP_CAPABILITY_SECRET")
_SECRET = _SECRET_STR.encode() if _SECRET_STR else b""

if not _SECRET:
    logger.warning("SCP_CAPABILITY_SECRET is missing. Using fallback dev-secret. DO NOT USE IN PRODUCTION.")
    _SECRET = b"dev-secret-do-not-use-in-prod-12345"

def mint_token(issuer: str, scope: str, capability_level: int, ttl_seconds: int = 3600) -> str:
    epoch = int(time.time())
    payload = {
        "iss": issuer,
        "scope": scope,
        "cap": capability_level,
        "iat": epoch,
        "exp": epoch + ttl_seconds,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"

def verify_token(token: str, required_scope: str = "*") -> dict:
    if not token or "." not in token:
        return {"valid": False, "error": "Invalid token format"}
    payload_b64, signature = token.rsplit(".", 1)
    
    expected_sig = hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        return {"valid": False, "error": "Invalid signature"}
    
    pad = len(payload_b64) % 4
    if pad:
        payload_b64 += "=" * (4 - pad)
        
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
    except Exception:
        return {"valid": False, "error": "Invalid payload"}
        
    if payload.get("exp", 0) < time.time():
        return {"valid": False, "error": "Token expired"}
        
    scope = payload.get("scope")
    if required_scope != "*" and scope != required_scope and scope != "*":
        return {"valid": False, "error": "Scope mismatch"}
        
    return {"valid": True, "payload": payload}
