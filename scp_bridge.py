"""
SCP DNA Bridge - dong bo du lieu tu SCP local len Hercules web app
==================================================================
Doc truc tiep cac file JSONL trong thu muc data/ cua SCP DNA
va day len Convex webhook. Khong can auth vao backend.

Cai dat:
    pip install requests

Chay test:
    python scp_bridge.py --test

Chay lien tuc (tail mode):
    python scp_bridge.py

Chay 1 lan (day toan bo du lieu hien co):
    python scp_bridge.py --backfill
"""

import json
import os
import sys
import time
import logging
from pathlib import Path

import requests

# ============================================================
# CAU HINH - SUA CAC GIA TRI NAY
# ============================================================
WEBHOOK_URL = "https://merry-blackbird-291.convex.site/api/scp/sync"
SECRET = os.getenv("SCP_WEBHOOK_SECRET", "scp-secret-2026")

# Thu muc chua SCP DNA (noi co folder data/)
SCP_ROOT = Path(os.getenv("SCP_ROOT", "."))
DATA_DIR = SCP_ROOT / "data"

# Backend API cua SCP (de lay health/status)
SCP_API = os.getenv("SCP_INTERNAL_URL", "http://127.0.0.1:8002")

POLL_SECONDS = int(os.getenv("SCP_POLL_SECONDS", "5"))
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bridge")

HEADERS = {"Authorization": "Bearer " + SECRET, "Content-Type": "application/json"}

# File JSONL -> loai du lieu tuong ung
JSONL_SOURCES = {
    "audit_findings.jsonl": "audit",
    "ai_threats.jsonl": "audit",
    "ai_harm_incidents.jsonl": "audit",
    "run_ledger.jsonl": "pipeline",
    "reflect.jsonl": "pipeline",
    "learning_lessons.jsonl": "query",
    "evolved_patterns.jsonl": "query",
}

# Vi tri doc cuoi cung cua tung file (byte offset)
OFFSET_FILE = SCP_ROOT / ".scp_bridge_offsets.json"


def load_offsets():
    if OFFSET_FILE.exists():
        try:
            return json.loads(OFFSET_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_offsets(offsets):
    try:
        OFFSET_FILE.write_text(json.dumps(offsets), encoding="utf-8")
    except Exception as e:
        log.warning("Cannot save offsets: " + str(e))


def post(payload):
    try:
        r = requests.post(WEBHOOK_URL, json=payload, headers=HEADERS, timeout=15)
        if r.ok:
            return True
        if r.status_code == 401:
            log.error("401 Unauthorized - SCP_WEBHOOK_SECRET chua duoc them vao Hercules Secrets!")
        else:
            log.warning("HTTP " + str(r.status_code) + ": " + r.text[:150])
    except Exception as e:
        log.error("Post error: " + str(e))
    return False


def to_str(value, default=""):
    if value is None:
        return default
    return str(value)


def to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def map_audit(rec, filename):
    """Map mot record JSONL sang audit payload."""
    actor = rec.get("actor") or rec.get("source") or rec.get("scanner") or "scp"
    action = (
        rec.get("action")
        or rec.get("type")
        or rec.get("category")
        or rec.get("severity")
        or filename.replace(".jsonl", "")
    )
    target = rec.get("target") or rec.get("file") or rec.get("path") or rec.get("id") or "/"
    result = rec.get("result") or rec.get("status") or rec.get("verdict") or "SUCCESS"
    result = to_str(result).upper()
    if result not in ("SUCCESS", "FAILURE", "FAIL", "ERROR", "DENIED"):
        result = "SUCCESS" if result in ("PASS", "OK", "FIXED", "VERIFIED") else "FAILURE"
    if result in ("FAIL", "ERROR", "DENIED"):
        result = "FAILURE"

    details = rec.get("message") or rec.get("description") or rec.get("title")

    return {
        "type": "audit",
        "data": {
            "actor": to_str(actor, "scp")[:120],
            "action": to_str(action)[:120],
            "target": to_str(target)[:200],
            "result": result,
            "ip": rec.get("ip") or "127.0.0.1",
            "details": to_str(details)[:500] if details else None,
        },
    }


def map_pipeline(rec, filename):
    """Map mot record run ledger / reflect sang pipeline payload."""
    session = (
        rec.get("request_id")
        or rec.get("run_id")
        or rec.get("session_id")
        or rec.get("trace_id")
        or "run_" + to_str(rec.get("ts") or int(time.time()))
    )
    stage_name = (
        rec.get("action")
        or rec.get("stage")
        or rec.get("phase")
        or rec.get("step")
        or filename.replace(".jsonl", "")
    )
    status_raw = to_str(rec.get("status") or rec.get("outcome") or "done").lower()
    if status_raw in ("ok", "success", "fixed", "verified", "pass", "completed"):
        status = "done"
    elif status_raw in ("error", "fail", "failed", "reject", "rejected"):
        status = "error"
    elif status_raw in ("running", "in_progress", "pending"):
        status = "running"
    else:
        status = "done"

    message = (
        rec.get("message")
        or rec.get("lesson")
        or rec.get("reflection")
        or rec.get("note")
        or to_str(stage_name)
    )

    duration = rec.get("duration_ms") or rec.get("elapsed_ms") or rec.get("latency_ms")

    return {
        "type": "pipeline",
        "data": {
            "sessionId": to_str(session)[:120],
            "stage": to_int(rec.get("stage_index") or rec.get("stage_num") or 0),
            "stageName": to_str(stage_name)[:120],
            "status": status,
            "message": to_str(message)[:400],
            "durationMs": to_int(duration) or None,
        },
    }


def map_query(rec, filename):
    """Map learning lesson / evolved pattern sang query payload."""
    question = (
        rec.get("question")
        or rec.get("lesson")
        or rec.get("pattern")
        or rec.get("title")
        or rec.get("description")
        or "SCP learning record"
    )
    verdict_raw = to_str(rec.get("verdict") or rec.get("status") or "VERIFIED").upper()
    if verdict_raw in ("PASS", "OK", "FIXED", "VERIFIED", "TRUE"):
        verdict = "VERIFIED"
    elif verdict_raw in ("FAIL", "FALSE", "REJECTED", "CONTRADICTED"):
        verdict = "CONTRADICTED"
    elif verdict_raw in ("PARTIAL", "UNCERTAIN", "REVIEW"):
        verdict = "PARTIAL"
    else:
        verdict = "UNKNOWN"

    confidence = rec.get("confidence")
    if confidence is None:
        confidence = rec.get("score") or rec.get("trust") or 0.75

    return {
        "type": "query",
        "data": {
            "question": to_str(question)[:500],
            "verdict": verdict,
            "confidence": min(max(to_float(confidence, 0.75), 0.0), 1.0),
            "processingTimeMs": to_int(rec.get("duration_ms") or rec.get("elapsed_ms") or 0),
        },
    }


MAPPERS = {"audit": map_audit, "pipeline": map_pipeline, "query": map_query}


def process_file(filepath, kind, offsets, max_records=200):
    """Doc cac dong moi trong file JSONL va day len webhook."""
    name = filepath.name
    start = offsets.get(name, 0)
    size = filepath.stat().st_size

    # File bi truncate/xoay vong -> doc lai tu dau
    if size < start:
        log.info(name + " truncated, reading from start")
        start = 0

    if size == start:
        return 0

    sent = 0
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        f.seek(start)
        for line in f:
            line = line.strip()
            if not line:
                continue
            if sent >= max_records:
                break
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not isinstance(rec, dict):
                continue
            payload = MAPPERS[kind](rec, name)
            if post(payload):
                sent += 1
        offsets[name] = f.tell()

    if sent:
        log.info("Synced " + str(sent) + " records from " + name)
    return sent


def scan_once(offsets):
    """Quet tat ca file JSONL mot lan."""
    if not DATA_DIR.exists():
        log.warning("Khong tim thay thu muc: " + str(DATA_DIR.resolve()))
        log.warning("Chay bridge tu thu muc goc SCP, hoac dat SCP_ROOT=C:\\duong\\dan\\scp")
        return 0

    total = 0
    for filename, kind in JSONL_SOURCES.items():
        fp = DATA_DIR / filename
        if fp.exists():
            total += process_file(fp, kind, offsets)

    # Quet them cac file .jsonl khac chua biet -> coi la audit
    for fp in DATA_DIR.glob("*.jsonl"):
        if fp.name not in JSONL_SOURCES:
            total += process_file(fp, "audit", offsets)

    save_offsets(offsets)
    return total


def sync_health():
    """Lay health tu backend SCP va day len nhu mot audit event."""
    try:
        r = requests.get(SCP_API + "/health", timeout=5)
        ok = r.ok
        post({
            "type": "audit",
            "data": {
                "actor": "scp_backend",
                "action": "HEALTH_CHECK",
                "target": SCP_API + "/health",
                "result": "SUCCESS" if ok else "FAILURE",
                "ip": "127.0.0.1",
                "details": r.text[:300] if ok else "HTTP " + str(r.status_code),
            },
        })
        return ok
    except Exception as e:
        log.debug("SCP backend khong phan hoi: " + str(e))
        return False


def run_test():
    log.info("=== SCP Bridge Test ===")
    try:
        r = requests.get(WEBHOOK_URL.replace("/sync", "/health"), timeout=10)
        log.info("Webhook health: " + str(r.json()))
    except Exception as e:
        log.error("Khong ket noi duoc webhook: " + str(e))
        return False

    ts = str(int(time.time()))
    results = [
        post({"type": "query", "data": {
            "question": "[TEST] SCP DNA bridge connected " + ts,
            "verdict": "VERIFIED", "confidence": 0.95, "processingTimeMs": 120}}),
        post({"type": "audit", "data": {
            "actor": "scp_bridge", "action": "BRIDGE_CONNECT",
            "target": "/api/scp/sync", "result": "SUCCESS", "ip": "127.0.0.1"}}),
        post({"type": "pipeline", "data": {
            "sessionId": "bridge_test_" + ts, "stage": 0, "stageName": "Bridge Test",
            "status": "done", "message": "SCP DNA bridge OK", "durationMs": 42}}),
    ]
    if all(results):
        log.info("TEST PASSED - Mo https://scp.onhercules.app/scp/ask de xem du lieu")
        return True
    log.error("TEST FAILED - Them SCP_WEBHOOK_SECRET vao Hercules: Advanced > Secrets")
    return False


def run_backfill():
    log.info("=== Backfill: day toan bo du lieu hien co ===")
    log.info("Data dir: " + str(DATA_DIR.resolve()))
    offsets = {}  # bat dau tu 0 de doc het
    total = scan_once(offsets)
    log.info("Backfill xong: " + str(total) + " records")


def run_tail():
    log.info("=== SCP Bridge - tail mode ===")
    log.info("Data dir : " + str(DATA_DIR.resolve()))
    log.info("Webhook  : " + WEBHOOK_URL)
    log.info("Poll     : moi " + str(POLL_SECONDS) + " giay")
    log.info("Nhan Ctrl+C de dung")

    offsets = load_offsets()
    ticks = 0
    while True:
        try:
            scan_once(offsets)
            ticks += 1
            # Moi 12 vong (~1 phut) day health len 1 lan
            if ticks % 12 == 1:
                sync_health()
        except KeyboardInterrupt:
            log.info("Bridge stopped.")
            break
        except Exception as e:
            log.warning("Scan error: " + str(e))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test" in args:
        run_test()
    elif "--backfill" in args:
        run_backfill()
    else:
        run_tail()
