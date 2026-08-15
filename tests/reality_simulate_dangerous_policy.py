from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scp.autofix.policy_gate import ImmutableAuditLog, PolicyFix, PolicyGate


CASES = {
    "benign_encoding_patch": 'open(path, "r", encoding="utf-8")',
    "shell_true": 'subprocess.run(command, shell=True)',
    "os_system": 'os.system(command)',
    "eval": 'value = eval(user_input)',
    "exec": 'exec(user_code)',
    "disable_tls": 'requests.get(url, verify=False)',
    "skip_auth": 'skip auth verification before applying fix',
    "delete_check": 'remove the validation check',
}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scp-policy-sim-") as tmp:
        log = Path(tmp) / "policy_blocks.jsonl"
        gate = PolicyGate(audit_log=ImmutableAuditLog(str(log)))
        results = {}
        for name, patch in CASES.items():
            decision = gate.evaluate_fix(
                PolicyFix(
                    fix_id=f"simulation-{name}",
                    patch=patch,
                    patched_source=patch,
                    bug_file="SIMULATION_ONLY.py",
                )
            )
            results[name] = {
                "allowed": decision.allowed,
                "severity": decision.severity,
                "blocked_patterns": decision.blocked_patterns,
            }
        chain_ok, chain_message = gate.audit_log.verify_chain()
        print(json.dumps({"results": results, "audit_chain_ok": chain_ok, "audit_chain": chain_message}, sort_keys=True))


if __name__ == "__main__":
    main()
