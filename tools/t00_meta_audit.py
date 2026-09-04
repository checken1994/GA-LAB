#!/usr/bin/env python3
"""SCP T00 Meta-Audit & Test-Integrity Authority (L2/L3)

This script enforces SCP's test integrity policies by strictly monitoring
test modifications, skips, deletions, and manufactured evidence against
a trusted baseline.

Violations already existing in the baseline are tracked as BASELINE_DEBT.
New violations added by the candidate branch are REJECTED.
Delta is computed using a finding-set (Counter) to prevent spoofing
by adding a violation and removing another.
"""
import sys
import yaml
import subprocess
import ast
import re
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = PROJECT_ROOT / "spec" / "guardrail_policy.yaml"

def fail_closed(msg):
    print(f"\n[T00 FAIL-CLOSED] {msg}")
    sys.exit(1)

def load_policy():
    if not POLICY_FILE.exists():
        fail_closed("Policy file spec/guardrail_policy.yaml is missing.")
    try:
        with open(POLICY_FILE, "r", encoding="utf-8") as f:
            policy = yaml.safe_load(f)
            if not policy:
                fail_closed("Policy file is empty or invalid YAML.")
            if "enforcement_context" not in policy:
                fail_closed("Policy missing 'enforcement_context'.")
            return policy
    except Exception as e:
        fail_closed(f"Failed to parse policy: {e}")

def run_git_cmd(args, check=False):
    try:
        res = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=PROJECT_ROOT)
        if check and res.returncode != 0:
            fail_closed(f"Git command failed: {' '.join(args)}\n{res.stderr}")
        return res.stdout.strip()
    except Exception as e:
        if check:
            fail_closed(f"Git execution error: {e}")
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
        self.findings = Counter()
        self.current_func = "<module>"
        self.test_funcs = set()
        
    def visit_FunctionDef(self, node):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._handle_function(node)

    def _handle_function(self, node):
        old = self.current_func
        self.current_func = node.name
        if node.name.startswith("test_"):
            self.test_funcs.add(node.name)
            
        for dec in node.decorator_list:
            attr_name = None
            if isinstance(dec, ast.Attribute):
                attr_name = dec.attr
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Attribute):
                    attr_name = dec.func.attr
                elif isinstance(dec.func, ast.Name):
                    attr_name = dec.func.id
                    
            if attr_name in ('skip', 'xfail', 'skipif'):
                self.findings[f"{attr_name} in {self.current_func}"] += 1
                
        self.generic_visit(node)
        self.current_func = old

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            if getattr(node.func.value, 'id', '') == 'pytest' and node.func.attr in ('skip', 'xfail', 'importorskip'):
                self.findings[f"pytest.{node.func.attr}() in {self.current_func}"] += 1
        self.generic_visit(node)

def get_fa01_signatures(code: str):
    """FA-01: Collect skip, xfail, skipif, importorskip occurrences using AST."""
    if not code: return Counter(), set()
    try:
        tree = ast.parse(code)
        visitor = AuditVisitor()
        visitor.visit(tree)
        return visitor.findings, visitor.test_funcs
    except SyntaxError:
        return Counter(), set()

def get_fa04_signatures(code: str) -> Counter:
    """FA-04: Collect manufactured VERIFIED claims using regex."""
    findings = Counter()
    if not code: return findings
    for i, line in enumerate(code.splitlines()):
        content = line.strip()
        if re.search(r'["\']simulated\s+verifi(ed|cation)["\']', content, re.IGNORECASE):
            findings[f"simulated verification: {content}"] += 1
        if re.search(r'return\s*\{.*["\']status["\'].*["\']VERIFIED["\']', content, re.IGNORECASE):
            findings[f"hardcoded VERIFIED: {content}"] += 1
    return findings

def audit_content(candidate_code: str, baseline_code: str, path: str):
    """Compare candidate against baseline for a single file using Counter delta.
    Returns (new_violations, baseline_debt, c_funcs, b_funcs).
    """
    new_violations = []
    debts = []
    c_funcs = set()
    b_funcs = set()
    
    # FA-01 and FA-02 (Test Weakening and Test Function Tracking)
    if (path.startswith("tests/") or path.startswith("scp/tests/")) and path.endswith(".py"):
        c_fa01, c_local_funcs = get_fa01_signatures(candidate_code)
        b_fa01, b_local_funcs = get_fa01_signatures(baseline_code)
        
        c_funcs = {f"{path}::{f}" for f in c_local_funcs}
        b_funcs = {f"{path}::{f}" for f in b_local_funcs}
        
        delta = c_fa01 - b_fa01
        for sig, count in delta.items():
            new_violations.append(f"FA-01: {path} -> {sig} ({count} new instances)")
            
        debt = c_fa01 & b_fa01
        for sig, count in debt.items():
            debts.append(f"FA-01: {path} -> {sig} ({count} historical instances)")
            
    # FA-04: Manufactured Green
    if path.startswith("scp/") and path.endswith(".py"):
        c_fa04 = get_fa04_signatures(candidate_code)
        b_fa04 = get_fa04_signatures(baseline_code)
        
        delta = c_fa04 - b_fa04
        for sig, count in delta.items():
            new_violations.append(f"FA-04: {path} -> {sig} ({count} new instances)")
            
        debt = c_fa04 & b_fa04
        for sig, count in debt.items():
            debts.append(f"FA-04: {path} -> {sig} ({count} historical instances)")
            
    return new_violations, debts, c_funcs, b_funcs

def check_code_owner_violations(policy):
    """L4: Warn on modification of protected paths."""
    changed_files = run_git_cmd(["diff", "--cached", "--name-only"]).splitlines()
    if not changed_files:
        changed_files = run_git_cmd(["diff", "--name-only"]).splitlines()
        
    protected = policy.get("protected_paths", [])
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
    trusted_base = policy["enforcement_context"].get("trusted_base", "origin/main")
    
    res = run_git_cmd(["rev-parse", "--verify", trusted_base])
    if not res:
        fail_closed(f"Trusted base '{trusted_base}' is invalid or missing. Run 'git fetch'.")
        
    print(f"[T00 Meta-Audit] Starting Test-Integrity Regression Authority...")
    print(f"[T00 Meta-Audit] Trusted Base: {trusted_base}")
    print("\n--- SCOPE & LIMITATIONS ---")
    print(" * FA-01 (Semantic Weakening): Partial (skip/xfail checked). Logic weakening requires L4 human review.")
    print(" * FA-03 (Same-SHA Evidence): NOT ENFORCED by T00 (Requires dedicated evidence tool).")
    print(" * FA-04 (Manufactured Green): Regex-based. Complex AST tracking requires L4 human review.")
    print(" * FA-05 (Self-Granting Auth): NOT ENFORCED by T00 (Requires capability scanner).")
    
    all_new_violations = []
    all_debts = []
    
    all_paths = set()
    # 1. Local files
    for p in PROJECT_ROOT.rglob("*.py"):
        rel_path = p.relative_to(PROJECT_ROOT).as_posix()
        if rel_path.startswith("tests/") or rel_path.startswith("scp/"):
            all_paths.add(rel_path)
            
    # 2. Baseline files
    out = run_git_cmd(["ls-tree", "-r", "--name-only", trusted_base])
    for line in out.splitlines():
        if line.endswith(".py") and (line.startswith("tests/") or line.startswith("scp/")):
            all_paths.add(line)
            
    global_c_funcs = set()
    global_b_funcs = set()
    
    for path in all_paths:
        c_code = get_local_content(path)
        b_code = get_git_content(trusted_base, path)
        new_v, debts, c_funcs, b_funcs = audit_content(c_code, b_code or "", path)
        all_new_violations.extend(new_v)
        all_debts.extend(debts)
        global_c_funcs.update(c_funcs)
        global_b_funcs.update(b_funcs)
        
    # Check FA-02 Test Deletion (comparing global function sets)
    deleted_tests = global_b_funcs - global_c_funcs
    for dt in deleted_tests:
        all_new_violations.append(f"FA-02: Deleted test function/nodeid: {dt}")
        
    l4_violations = check_code_owner_violations(policy)
    
    if all_debts:
        print("\n--- BASELINE_DEBT (Tracked, Not Blocking) ---")
        for debt in sorted(all_debts):
            print(f" [DEBT] {debt}")
            
    if l4_violations:
        print("\n--- L4 CODEOWNERS (Warning) ---")
        for v in l4_violations:
            print(f" [L4] {v}")
        print("Note: L4 is VERIFIED only by GitHub Server-Side Ruleset. This is a local warning.")

    if all_new_violations:
        print("\n" + "="*60)
        print("T00 META-AUDIT FAILED - NEW REGRESSIONS DETECTED")
        print("="*60)
        for v in sorted(all_new_violations):
            print(f" [FAIL] {v}")
        print("\nFix violations before proceeding.")
        sys.exit(1)
        
    print("\n[T00 Meta-Audit] All integrity checks passed (0 new regressions).")
    sys.exit(0)

if __name__ == "__main__":
    main()
