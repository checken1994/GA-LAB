import re

with open(r"c:\Users\check\Downloads\scp\scp\api_server.py", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Add imports
imports_to_add = """
# --- SCP V3 ENTERPRISE IMPORTS ---
from fastapi import Depends
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Histogram
from fastapi.responses import Response
from scp.security.jwt_guard import get_current_user
from scp.observability.telemetry import setup_telemetry

# Enterprise Metrics
REQUEST_COUNT = Counter("scp_request_count", "Total SCP Requests", ["method", "endpoint"])
REQUEST_LATENCY = Histogram("scp_request_latency_seconds", "Request latency", ["endpoint"])
"""

if "SCP V3 ENTERPRISE IMPORTS" not in text:
    text = text.replace("import asyncio", imports_to_add + "\nimport asyncio", 1)

# 2. Add Limiter and Telemetry right after FastAPI app creation
app_init_patch = """app = FastAPI(
    title=f"{RELEASE_LABEL} - Self-Correcting Pipeline API",
    description=f"{DOMAIN_EXPERT_ENSEMBLE_TERM} + FalsificationEngine + Governance + Chat + Evolution",
    version=_SCP_VERSION,
    lifespan=lifespan,
)

# --- SCP V3 ENTERPRISE MIDDLEWARE ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

try:
    setup_telemetry(app)
except Exception as e:
    logger.warning(f"Telemetry setup skipped: {e}")

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
"""

text = re.sub(r'app\s*=\s*FastAPI\([\s\S]*?lifespan=lifespan,\s*\)', app_init_patch, text)

# 3. Add Rate Limit and JWT to /ask
ask_route_patch = """@app.post("/ask", response_model=AskResponse)
@limiter.limit("60/minute")
@traced_request(_REQUEST_RUN_LEDGER)
async def ask(req: AskRequest, request: Request, current_user: str = Depends(get_current_user)):
    REQUEST_COUNT.labels(method="POST", endpoint="/ask").inc()
"""

# The exact original text for /ask is:
# @app.post("/ask", response_model=AskResponse)
# @traced_request(_REQUEST_RUN_LEDGER)
# async def ask(req: AskRequest, request: Request):

text = re.sub(
    r'@app\.post\("/ask", response_model=AskResponse\)\s*@traced_request\(_REQUEST_RUN_LEDGER\)\s*async def ask\(req: AskRequest, request: Request\):',
    ask_route_patch,
    text
)

with open(r"c:\Users\check\Downloads\scp\scp\api_server.py", "w", encoding="utf-8") as f:
    f.write(text)
