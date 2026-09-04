#!/usr/bin/env python3
"""SCP T00 Meta-Audit & Test-Integrity Authority (L2/L3)

This script enforces SCP's test integrity policies by strictly monitoring
test modifications, skips, deletions, and manufactured evidence against
a trusted baseline (origin/main).

Violations already existing in the baseline are tracked as BASELINE_DEBT.
New violations added by the candidate branch are REJECTED.
"""
import sys
import yaml
import subprocess
import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = PROJECT_ROOT / "spec" / "guardrail_policy.yaml"

def load_policy():
    if not POLICY_FILE.exists():
        return None
    with open(POLICY_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run_git_cmd(args):
    try:
        res = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=PROJECT_ROOT)
        return res.stdout.strip()
    except Exception:
        return ""

def get_git_content(ref, path):
    """Fetch content of a file at a specific git ref."""
    try:
        out = subprocess.check_output(
            ["git", "show", f"{ref}:{path}"], 
            stderr=subprocess.DEVNULL, cwd=PROJECT_ROOT
        )
        return out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError:
        return None

def get_local_content(path):
    """Fetch local working tree content."""
    p = PROJECT_ROOT / path
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None

class AuditVisitor(ast.NodeVisitor):
    def __init__(self):
        self.skips = 0
        
    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            if getattr(node.func.value, 'id', '') == 'pytest' and node.func.attr in ('skip', 'xfail'):
                self.skips += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute) and dec.attr in ('skip', 'xfail'):
                self.skips += 1
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ('skip', 'xfail'):
                self.skips += 1
        self.generic_visit(node)

def count_fa01_skips(code: str) -> int:
    """FA-01: Count skip and xfail occurrences using AST."""
    if not code: return 0
    try:
        tree = ast.parse(code)
        visitor = AuditVisitor()
        visitor.visit(tree)
        return visitor.skips
    except SyntaxError:
        return 0

def count_fa04_manufactured(code: str) -> int:
    """FA-04: Count manufactured VERIFIED claims using regex."""
    if not code: return 0
    count = 0
    for line in code.splitlines():
        if re.search(r'["\']simulated\s+verifi(ed|cation)["\']', line, re.IGNORECASE):
            count += 1
        if re.search(r'return\s*\{.*["\']status["\'].*["\']VERIFIED["\']', line, re.IGNORECASE):
            count += 1
    return count

def audit_content(candidate_code: str, baseline_code: str, path: str):
    """Compare candidate against baseline for a single file.
    Returns (new_violations, baseline_debt).
    """
    new_violations = []
    debts = []
    
    # FA-01: Test Weakening
    if path.startswith("tests/") and path.endswith(".py"):
        c_skips = count_fa01_skips(candidate_code)
        b_skips = count_fa01_skips(baseline_code)
        if c_skips > b_skips:
            new_violations.append(f"FA-01: {path} (+{c_skips - b_skips} new skip/xfail)")
        elif c_skips > 0 and c_skips <= b_skips:
            debts.append(f"FA-01: {path} ({c_skips} historical skip/xfail)")
            
    # FA-04: Manufactured Green
    if path.startswith("scp/") and path.endswith(".py"):
        c_m = count_fa04_manufactured(candidate_code)
        b_m = count_fa04_manufactured(baseline_code)
        if c_m > b_m:
            new_violations.append(f"FA-04: {path} (+{c_m - b_m} new manufactured VERIFIED)")
        elif c_m > 0 and c_m <= b_m:
            debts.append(f"FA-04: {path} ({c_m} historical manufactured VERIFIED)")
            
    return new_violations, debts

def check_test_deletion(baseline_ref="origin/main"):
    """FA-02: Prevent test deletion relative to baseline."""
    violations = []
    # Use ls-tree to get all tests in baseline
    out = run_git_cmd(["ls-tree", "-r", "--name-only", baseline_ref, "tests/"])
    baseline_tests = [line for line in out.splitlines() if line.endswith('.py')]
    
    for test in baseline_tests:
        if not (PROJECT_ROOT / test).exists():
            violations.append(f"FA-02: Deleted test file {test}")
            
    return violations

def check_code_owner_violations(policy):
    """L4: Warn on modification of protected paths."""
    changed_files = run_git_cmd(["diff", "--cached", "--name-only"]).splitlines()
    if not changed_files:
        changed_files = run_git_cmd(["diff", "--name-only"]).splitlines()
        
    protected = policy.get("protected_paths", []) if policy else []
    violations = []
    for f in changed_files:
        if not f: continue
        for p in protected:
            if f.startswith(p.strip('/')):
                violations.append(f"L4 Protected Path Modified: {f}")
                break
    return violations

def main():
    policy = load_policy()
    trusted_base = "origin/main"
    if policy and "enforcement_context" in policy:
        trusted_base = policy["enforcement_context"].get("trusted_base", "origin/main")
        
    print(f"[T00 Meta-Audit] Starting Test-Integrity Regression Authority...")
    print(f"[T00 Meta-Audit] Trusted Base: {trusted_base}")
    
    all_new_violations = []
    all_debts = []
    
    # Check FA-02 Test Deletion
    all_new_violations.extend(check_test_deletion(trusted_base))
    
    # Get all python files in tests/ and scp/ for FA-01 and FA-04
    local_files = []
    for p in PROJECT_ROOT.rglob("*.py"):
        rel_path = p.relative_to(PROJECT_ROOT).as_posix()
        if rel_path.startswith("tests/") or rel_path.startswith("scp/"):
            local_files.append(rel_path)
            
    for path in local_files:
        c_code = get_local_content(path)
        b_code = get_git_content(trusted_base, path)
        new_v, debts = audit_content(c_code, b_code or "", path)
        all_new_violations.extend(new_v)
        all_debts.extend(debts)
        
    # Check L4 
    l4_violations = check_code_owner_violations(policy)
    
    if all_debts:
        print("\n--- BASELINE_DEBT (Tracked, Not Blocking) ---")
        for debt in all_debts:
            print(f" ⚠️  {debt}")
            
    if l4_violations:
        print("\n--- L4 CODEOWNERS (Warning) ---")
        for v in l4_violations:
            print(f" 🛡️  {v}")
        print("Note: L4 is VERIFIED only by GitHub Server-Side Ruleset. This is a local warning.")

    if all_new_violations:
        print("\n" + "="*60)
        print("T00 META-AUDIT FAILED - NEW REGRESSIONS DETECTED")
        print("="*60)
        for v in all_new_violations:
            print(f" ❌ {v}")
        print("\nFix violations before proceeding.")
        sys.exit(1)
        
    print("\n[T00 Meta-Audit] All integrity checks passed (0 new regressions). ✓")
    sys.exit(0)

if __name__ == "__main__":
    main()
