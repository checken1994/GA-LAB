#!/usr/bin/env python3
"""Deterministic hourly SCP runtime and capability monitor.

This monitor is intentionally read-only. It probes local health/readiness and
Hands policy-preview endpoints; it never executes a write, browser submission,
process mutation, upload, delete, or external side effect. It writes only
private, redacted telemetry under the configured root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scp.security.url_safety import safe_urlopen

DEFAULT_ENDPOINTS = {
    "backend": "http://127.0.0.1:8000/health",
    "backend_detailed": "http://127.0.0.1:8000/health/detailed",
    "scheduler": "http://127.0.0.1:3030/healthz",
    "dashboard": "http://127.0.0.1:3000/",
    "ollama": "http://127.0.0.1:11434/api/tags",
    "hands_status": "http://127.0.0.1:8000/v3/hands/status",
    "hands_capabilities": "http://127.0.0.1:8000/v3/hands/capabilities",
    "hands_plan": "http://127.0.0.1:8000/v3/hands/plan",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _body_summary(body: bytes) -> dict[str, Any]:
    return {
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _decode_json(body: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(body.decode("utf-8", errors="replace"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def probe_http(url: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 8.0) -> dict[str, Any]:
    """Probe an endpoint and retain only redacted metadata plus safe policy fields."""
    started = time.perf_counter()
    body = b""
    status: int | None = None
    error_type = ""
    try:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        response_request = Request(url, data=data, headers=headers, method=method)
        # [SEC-S6] SSRF guard: probes go through safe_urlopen. The monitored
        # endpoints are intentional loopback targets, so internal hosts are
        # explicitly allowed here.
        with safe_urlopen(response_request, timeout=timeout, allow_internal=True) as response:
            status = int(response.status)
            body = response.read(1_048_576)
    except HTTPError as exc:
        status = int(exc.code)
        try:
            body = exc.read(1_048_576)
        except OSError:
            body = b""
        error_type = "HTTPError"
    except (OSError, URLError, TimeoutError) as exc:
        error_type = type(exc).__name__
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    result: dict[str, Any] = {
        "url": url,
        "method": method,
        "status": status,
        "ok": status == 200,
        "elapsed_ms": elapsed_ms,
        "error_type": error_type,
        **_body_summary(body),
    }
    decoded = _decode_json(body)
    if decoded is not None:
        safe_fields = ("success", "allowed", "requiresApproval", "error", "plannerVersion", "version")
        for field in safe_fields:
            if field in decoded and isinstance(decoded[field], (bool, int, float, str, type(None))):
                result[field] = decoded[field]
        if isinstance(decoded.get("policy"), dict):
            policy = decoded["policy"]
            for field in ("risk", "capabilityLevel", "requiresApproval", "verifier", "rollback"):
                if field in policy and isinstance(policy[field], (bool, int, float, str, type(None))):
                    result[f"policy_{field}"] = policy[field]
    return result


def port_probe(host: str, port: int, timeout: float = 2.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"host": host, "port": port, "listening": True, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
    except OSError as exc:
        return {"host": host, "port": port, "listening": False, "error_type": type(exc).__name__, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}


def policy_payload(action: str, capability_level: int, approved: bool) -> dict[str, Any]:
    return {
        "action": action,
        "params": {},
        "capabilityLevel": capability_level,
        "approved": approved,
        "dryRun": True,
    }


def evaluate_policy(policy_results: dict[str, dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    required_denials = {
        "write_l0_no_approval": (False, "write L0 must be denied"),
        "write_l3_no_approval": (False, "write L3 without approval must be denied"),
        "unknown_action": (False, "unknown action must be denied"),
    }
    for name, (expected, reason) in required_denials.items():
        observed = policy_results.get(name, {}).get("allowed")
        if observed is not expected:
            failures.append(f"{name}: {reason}; observed={observed!r}")
    if policy_results.get("status_l0", {}).get("allowed") is not True:
        failures.append("status_l0: read-only status should be allowed at L0")
    if policy_results.get("write_l3_approved", {}).get("allowed") is not True:
        failures.append("write_l3_approved: policy preview should permit only after capability and approval; no action was executed")
    return failures


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def run_monitor(root: Path, timeout: float = 8.0) -> dict[str, Any]:
    root = root.resolve()
    endpoints = dict(DEFAULT_ENDPOINTS)
    http: dict[str, dict[str, Any]] = {}
    for name in ("backend", "backend_detailed", "scheduler", "dashboard", "ollama", "hands_status", "hands_capabilities"):
        http[name] = probe_http(endpoints[name], timeout=timeout)

    policy_results = {
        "status_l0": probe_http(endpoints["hands_plan"], method="POST", payload=policy_payload("pc.status", 0, False), timeout=timeout),
        "write_l0_no_approval": probe_http(endpoints["hands_plan"], method="POST", payload=policy_payload("pc.write_file", 0, False), timeout=timeout),
        "write_l3_no_approval": probe_http(endpoints["hands_plan"], method="POST", payload=policy_payload("pc.write_file", 3, False), timeout=timeout),
        "write_l3_approved": probe_http(endpoints["hands_plan"], method="POST", payload=policy_payload("pc.write_file", 3, True), timeout=timeout),
        "unknown_action": probe_http(endpoints["hands_plan"], method="POST", payload=policy_payload("pc.unknown_probe", 0, False), timeout=timeout),
    }

    ports = {str(port): port_probe("127.0.0.1", port) for port in (3000, 3030, 8000, 11434)}
    failures: list[str] = []
    for name in ("backend", "backend_detailed", "scheduler", "dashboard", "ollama", "hands_status", "hands_capabilities"):
        if not http[name]["ok"]:
            failures.append(f"{name}: HTTP readiness failed ({http[name].get('status') or http[name].get('error_type')})")
    failures.extend(evaluate_policy(policy_results))
    sentinel = root / "probe-never-write.txt"
    if sentinel.exists():
        failures.append("sentinel: probe-never-write.txt exists; read-only monitor invariant violated")

    return {
        "schema_version": "scp-hourly-monitor-v1",
        "timestamp_utc": utc_now(),
        "root": str(root),
        "profile": "shadow_read_only_capability_preview",
        "status": "PASS" if not failures else "DEGRADED",
        "failures": failures,
        "ports": ports,
        "http": http,
        "policy_preview": policy_results,
        "side_effects_executed": False,
        "sentinel_exists": sentinel.exists(),
    }


def persist(record: dict[str, Any], root: Path) -> None:
    evidence_dir = root / ".private-secrets" / "release-audit" / "scp-247"
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with (evidence_dir / "hourly-monitor.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    atomic_write(evidence_dir / "hourly-latest.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    try:
        record = run_monitor(args.root, timeout=max(1.0, min(args.timeout, 30.0)))
        persist(record, args.root.resolve())
    except Exception as exc:  # noqa: BLE001 - monitor must persist every unexpected failure
        record = {
            "schema_version": "scp-hourly-monitor-v1",
            "timestamp_utc": utc_now(),
            "root": str(args.root.resolve()),
            "profile": "shadow_read_only_capability_preview",
            "status": "FAIL",
            "failures": [f"monitor_exception:{type(exc).__name__}"],
            "side_effects_executed": False,
        }
        try:
            persist(record, args.root.resolve())
        except OSError:
            pass
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
