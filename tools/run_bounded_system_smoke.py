"""Run the bounded local SCP smoke used by the release evidence gate.

This deliberately binds only to 127.0.0.1:8002, denies external egress, uses
isolated temporary state, and checks both startup behavior and post-stop port
cleanup. It is a bounded proof, not a production or distributed benchmark.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8002"


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    response = requests.request(method, f"{BASE}{path}", json=payload, timeout=30)
    item: dict[str, object] = {"http_status": response.status_code}
    try:
        item["body"] = response.json()
    except ValueError:
        item["body_text"] = response.text[:1000]
    return item


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.iterdir():
        if path.is_file():
            path.unlink()
    if port_open(8000):
        raise RuntimeError("refused: port 8000 already in use")
    if port_open(8002):
        raise RuntimeError("refused: port 8002 already in use")

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "SCP_HOST": "127.0.0.1",
            "SCP_PORT": "8002",
            "SCP_MODE": "test",
            "SCP_EGRESS_MODE": "deny",
            "SCP_WEB_FALLBACK": "0",
            "SCP_ASK_KERNEL_ENABLED": "1",
            "SCP_KERNEL_DB_PATH": str(output_dir / "kernel.sqlite3"),
            "SCP_KERNEL_TRACE_PATH": str(output_dir / "kernel_trace.jsonl"),
            "SCP_REQUEST_RUN_LEDGER_PATH": str(output_dir / "request_runs.jsonl"),
            "SCP_HANDS_LOCAL_ONLY": "1",
            "SCP_ENV_FILE": str(output_dir / "empty.env"),
        }
    )
    (output_dir / "empty.env").write_text("", encoding="utf-8")
    log_path = output_dir / "server.log"
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "scp", "8002"],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    responses: dict[str, dict] = {}
    report: dict[str, object] | None = None
    try:
        ready = False
        for _ in range(60):
            try:
                response = requests.get(f"{BASE}/health", timeout=2)
                if response.status_code == 200:
                    ready = True
                    responses["health"] = {
                        "http_status": response.status_code,
                        "body": response.json(),
                    }
                    break
            except requests.RequestException:
                pass
            time.sleep(0.5)
        if not ready:
            raise RuntimeError("health did not become ready")

        checks_to_run = [
            ("hands_status", "GET", "/v3/hands/status", None),
            ("hands_actions", "GET", "/v3/hands/actions", None),
            (
                "hands_plan",
                "POST",
                "/v3/hands/plan",
                {"action": "pc.status", "params": {}, "capabilityLevel": 1, "approved": True, "dryRun": True},
            ),
            (
                "hands_execute_dry_run",
                "POST",
                "/v3/hands/execute",
                {"action": "pc.status", "params": {}, "capabilityLevel": 1, "approved": True, "dryRun": True},
            ),
            (
                "ask_rag",
                "POST",
                "/ask",
                {
                    "question": "What is spaced repetition?",
                    "domain": "consumer_travel_education",
                    "rag_enabled": True,
                    "contexts": [
                        "Spaced repetition is an evidence-based learning technique that is usually performed with flashcards."
                    ],
                    "retrieved_context": "Spaced repetition is an evidence-based learning technique that is usually performed with flashcards.",
                    "ai_answer": "Spaced repetition is an evidence-based learning technique that is usually performed with flashcards.",
                    "ground_truth": "Spaced repetition is an evidence-based learning technique that is usually performed with flashcards.",
                    "session_id": "release-gate-bounded-smoke",
                },
            ),
        ]
        for name, method, path, payload in checks_to_run:
            responses[name] = _request(method, path, payload)

        checks = {
            "health_200": responses["health"]["http_status"] == 200,
            "hands_status_200": responses["hands_status"]["http_status"] == 200,
            "hands_actions_200": responses["hands_actions"]["http_status"] == 200,
            "hands_plan_200": responses["hands_plan"]["http_status"] == 200,
            "hands_plan_allowed": responses["hands_plan"].get("body", {}).get("allowed") is True,
            "hands_execute_200": responses["hands_execute_dry_run"]["http_status"] == 200,
            "hands_execute_success": responses["hands_execute_dry_run"].get("body", {}).get("success") is True,
            "hands_execute_dry_run": responses["hands_execute_dry_run"].get("body", {}).get("dryRun") is True,
            "ask_http_200": responses["ask_rag"]["http_status"] == 200,
            "ask_verdict_pass": responses["ask_rag"].get("body", {}).get("verdict") == "PASS",
            "ask_run_status_success": responses["ask_rag"].get("body", {}).get("run_status") == "SUCCESS",
            "ask_ledger_status_ok": responses["ask_rag"].get("body", {}).get("ledger_status") == "OK",
        }
        report = {
            "schema_version": "scp-bounded-system-smoke-v2",
            "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "host": "127.0.0.1",
            "port": 8002,
            "port_8000_used": False,
            "egress_mode": "deny",
            "responses": responses,
            "checks": checks,
            "pass": all(checks.values()),
            "scope": "Bounded local smoke: API→router→ledger/kernel→RAG governance→Hands read-only dry-run. No external write, provider fallback, distributed deployment, or factual 1000-row benchmark.",
        }
        (output_dir / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not report["pass"]:
            raise RuntimeError("bounded system smoke checks failed")
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()

    time.sleep(0.5)
    cleanup = {
        "process_returncode": process.returncode,
        "port_8002_free": not port_open(8002),
        "port_8000_free": not port_open(8000),
    }
    (output_dir / "cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n", encoding="utf-8")
    if not cleanup["port_8002_free"] or not cleanup["port_8000_free"]:
        raise RuntimeError(f"port cleanup failed: {cleanup}")
    return {"evidence": str(output_dir / "evidence.json"), "cleanup": cleanup}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "bounded_system_smoke_ci")
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
