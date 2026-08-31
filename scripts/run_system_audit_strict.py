"""Strict system-level audit for an integration candidate.

This runner treats evidence as authoritative: every step has an explicit
postcondition and any missing/contradictory evidence fails the audit.
It intentionally uses isolated local state and denies external egress.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from scripts import run_full_audit as base
from tools.run_bounded_system_smoke import run as run_bounded_smoke

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "system_audit_strict"


def _run_step(name: str, fn) -> dict:
    started = time.time()
    try:
        result = fn()
        ok = bool(result.get("ok", False))
        return {
            "name": name,
            "status": "PASS" if ok else "FAIL",
            "elapsed_sec": round(time.time() - started, 2),
            **result,
        }
    except Exception as exc:
        return {
            "name": name,
            "status": "ERROR",
            "ok": False,
            "elapsed_sec": round(time.time() - started, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _validate_boot_findings(findings: dict) -> dict:
    health = findings.get("health", {})
    readiness = findings.get("readiness", {})
    brute = findings.get("auth_brute_force", {})
    auth = findings.get("auth_valid", {})
    rag = findings.get("rag_ask", {})
    attack = findings.get("prompt_injection", {})

    ready_checks = readiness.get("checks", {}) or {}
    rag_verdict = rag.get("verdict")
    rag_withheld = bool(rag.get("withheld"))

    # PASS must never coexist with a withheld answer. Conversely, a non-PASS
    # verdict must fail closed by withholding the answer. This remains valid
    # when the environment intentionally denies external egress.
    rag_fail_closed_coherent = (
        rag.get("status_code") == 200
        and (
            (rag_verdict == "PASS" and not rag_withheld)
            or (rag_verdict != "PASS" and rag_withheld)
        )
    )

    checks = {
        "health_200": health.get("status_code") == 200,
        "readiness_200": readiness.get("status_code") == 200,
        "judge_ready": ready_checks.get("judge") == "ok",
        "background_scheduler_ready": ready_checks.get("background_scheduler") == "ok",
        "auth_bruteforce_rate_limited": brute.get("rate_limited") is True and 429 in brute.get("codes", []),
        "auth_valid_token": auth.get("status_code") == 200 and auth.get("has_token") is True,
        "rag_fail_closed_coherent": rag_fail_closed_coherent,
        "prompt_injection_http_200": attack.get("status_code") == 200,
        "prompt_injection_not_pass": attack.get("verdict") != "PASS",
        "prompt_injection_withheld": attack.get("withheld") is True,
        "prompt_injection_killed": attack.get("governance") == "KILL",
    }
    return {"ok": all(checks.values()), "checks": checks, "findings": findings}


def step_boot_strict(env_file: str) -> dict:
    raw = base.step_boot_and_probe(env_file)
    return _validate_boot_findings(raw.get("findings", {}))


def step_contract_tests() -> dict:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_god_split_semantic_parity.py",
        "tests/test_provider_failover.py",
        "--tb=short",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "output_tail": (proc.stdout + "\n" + proc.stderr)[-4000:],
    }


def step_full_pytest() -> dict:
    result = base.step_pytest()
    return {**result, "ok": bool(result.get("ok"))}


def step_reality_suite() -> dict:
    result = base.step_reality()
    return {**result, "ok": bool(result.get("ok"))}


def step_fitness() -> dict:
    result = base.step_fitness()
    return {**result, "ok": bool(result.get("ok"))}


def step_hermetic_boot() -> dict:
    result = base.step_hermetic_boot()
    return {**result, "ok": bool(result.get("ok"))}


def step_bounded_smoke_twice() -> dict:
    first_dir = REPORT_DIR / "bounded_smoke_first"
    second_dir = REPORT_DIR / "bounded_smoke_restart"
    first = run_bounded_smoke(first_dir)
    second = run_bounded_smoke(second_dir)

    first_evidence = json.loads((first_dir / "evidence.json").read_text(encoding="utf-8"))
    second_evidence = json.loads((second_dir / "evidence.json").read_text(encoding="utf-8"))
    first_cleanup = json.loads((first_dir / "cleanup.json").read_text(encoding="utf-8"))
    second_cleanup = json.loads((second_dir / "cleanup.json").read_text(encoding="utf-8"))

    checks = {
        "first_smoke_pass": first_evidence.get("pass") is True,
        "first_port_cleanup": first_cleanup.get("port_8000_free") is True,
        "restart_smoke_pass": second_evidence.get("pass") is True,
        "restart_port_cleanup": second_cleanup.get("port_8000_free") is True,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "first": first,
        "second": second,
        "first_evidence": first_evidence,
        "second_evidence": second_evidence,
    }


def main() -> int:
    started = time.time()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()

    env_file = ROOT / ".env.system-audit-run"
    env_file.write_text(
        "SCP_JWT_SECRET=" + secrets.token_hex(32) + "\n"
        "SCP_ADMIN_KEY=" + secrets.token_urlsafe(24) + "\n",
        encoding="utf-8",
    )

    # Explicitly deny external egress for deterministic system evidence.
    os.environ.setdefault("SCP_EGRESS_MODE", "deny")
    os.environ.setdefault("SCP_PRODUCTION_MODE", "0")
    os.environ.setdefault("SCP_SKIP_STARTUP_GATE", "0")

    steps: list[dict] = []
    try:
        steps.append(_run_step("import_manifest", base.step_import_check))
        steps.append(_run_step("boot_and_probe_strict", lambda: step_boot_strict(str(env_file))))
        steps.append(_run_step("god_provider_contracts", step_contract_tests))
        steps.append(_run_step("full_pytest", step_full_pytest))
        steps.append(_run_step("reality_suite", step_reality_suite))
        steps.append(_run_step("fitness_golden_suite", step_fitness))
        steps.append(_run_step("hermetic_boot", step_hermetic_boot))
        steps.append(_run_step("bounded_smoke_and_restart", step_bounded_smoke_twice))
    finally:
        env_file.unlink(missing_ok=True)

    all_pass = all(step.get("status") == "PASS" for step in steps)
    report = {
        "schema_version": "scp-strict-system-audit-v1",
        "commit": commit,
        "started_at": started,
        "completed_at": time.time(),
        "elapsed_sec": round(time.time() - started, 2),
        "egress_mode": os.environ.get("SCP_EGRESS_MODE"),
        "steps": steps,
        "overall_verdict": "PASS_WITHIN_SCOPE" if all_pass else "BLOCKED",
        "scope": (
            "Isolated local system audit: boot/readiness, auth brute-force and valid token, "
            "fail-closed ask semantics, prompt-injection kill/withhold, GOD/provider contracts, "
            "full pytest, Reality suite, fitness suite, hermetic boot, and two sequential bounded "
            "API→router→ledger/kernel→RAG governance→Hands dry-run smoke cycles with port cleanup. "
            "No claim about external-provider availability or distributed production deployment."
        ),
    }
    report_path = REPORT_DIR / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "commit": commit,
        "overall_verdict": report["overall_verdict"],
        "steps": [{"name": s["name"], "status": s["status"]} for s in steps],
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
