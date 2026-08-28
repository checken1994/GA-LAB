import jwt
import os
import time
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any

# Enterprise Security: The JWT Secret should ideally come from environment variables.
JWT_SECRET = os.environ.get("SCP_JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("[SECURITY FATAL] SCP_JWT_SECRET is not set in environment. Zero-Trust requires a secure token secret.")

JWT_ALGORITHM = "HS256"

security = HTTPBearer()

def create_access_token(data: dict, expires_delta: int = 3600) -> str:
    """Create a new JWT token valid for `expires_delta` seconds."""
    to_encode = data.copy()
    expire = time.time() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict[str, Any]:
    """Verify the JWT token from the Authorization header."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(payload: Dict[str, Any] = Security(verify_jwt_token)) -> str:
    user = payload.get("sub")
    if user is None:
        raise HTTPException(status_code=401, detail="Token missing subject (sub)")
    return user
