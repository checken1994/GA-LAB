#!/usr/bin/env python3
"""SCP T00 Meta-Audit & Test-Integrity Authority (L2/L3)

This script enforces SCP's test integrity policies by strictly monitoring
test modifications, skips, deletions, and manufactured evidence.

Enforces:
- FA-01: No test weakening (specifically blocks new skip/xfail via AST).
- FA-02: No test deletion (via git diff against main).
- FA-04: No manufactured VERIFIED returns.
- L4: Warns on touching CODEOWNERS protected paths.
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

def check_test_deletion():
    """FA-02: Prevent test file deletion without architectural approval."""
    violations = []
    # Check what files are marked for deletion in the current branch compared to main
    diff_output = run_git_cmd(["diff", "--name-status", "origin/main...HEAD"])
    for line in diff_output.splitlines():
        if line.startswith("D\t") and "tests/" in line:
            filename = line.split("\t", 1)[1]
            violations.append(f"FA-02: Test deletion blocked -> {filename}")
    
    # Also check staged/unstaged deletions currently in working directory
    status_output = run_git_cmd(["status", "--short"])
    for line in status_output.splitlines():
        if line.startswith(" D ") or line.startswith("D "):
            filename = line[3:]
            if filename.startswith("tests/"):
                violations.append(f"FA-02: Local test deletion blocked -> {filename}")
                
    return list(set(violations))

class SkipXfailVisitor(ast.NodeVisitor):
    def __init__(self):
        self.found_skips = []
        
    def visit_Call(self, node):
        # Look for pytest.skip()
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest":
                if node.func.attr == "skip":
                    self.found_skips.append(node.lineno)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # Look for @pytest.mark.skip or @pytest.mark.xfail decorators
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Attribute):
                if decorator.attr in ("skip", "xfail") and isinstance(decorator.value, ast.Attribute) and decorator.value.attr == "mark":
                    self.found_skips.append(node.lineno)
            elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                if decorator.func.attr in ("skip", "xfail"):
                    self.found_skips.append(node.lineno)
        self.generic_visit(node)

def check_test_weakening():
    """FA-01: No test weakening (Detect skip/xfail via AST)."""
    violations = []
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.exists():
        return violations
        
    for py_file in tests_dir.rglob("test_*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            visitor = SkipXfailVisitor()
            visitor.visit(tree)
            for lineno in visitor.found_skips:
                violations.append(f"FA-01: skip/xfail found in {py_file.relative_to(PROJECT_ROOT)} at line {lineno}")
        except SyntaxError:
            violations.append(f"Syntax error parsing test file: {py_file.relative_to(PROJECT_ROOT)}")
        except Exception:
            pass
            
    # In a full implementation, we would compare the skip list against origin/main's baseline 
    # to only alert on *newly added* skips. For now, we alert on all (strict mode).
    return violations

def check_manufactured_green():
    """FA-04: No Manufactured VERIFIED"""
    violations = []
    scp_dir = PROJECT_ROOT / "scp"
    if not scp_dir.exists():
        return violations
        
    for path in scp_dir.rglob("*.py"):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            for line_num, line in enumerate(content.splitlines(), 1):
                if re.search(r'["\']simulated\s+verifi(ed|cation)["\']', line, re.IGNORECASE):
                    violations.append(f"FA-04: {path.relative_to(PROJECT_ROOT)}:{line_num} -> Simulated verification")
                if re.search(r'return\s*\{.*["\']status["\'].*["\']VERIFIED["\']', line, re.IGNORECASE):
                    violations.append(f"FA-04: {path.relative_to(PROJECT_ROOT)}:{line_num} -> Hardcoded VERIFIED return")
        except Exception:
            pass
    return violations

def check_code_owner_violations(policy):
    """L4 Enforcer: Check if AI is modifying protected paths autonomously."""
    changed_files = run_git_cmd(["diff", "--cached", "--name-only"]).splitlines()
    if not changed_files:
        changed_files = run_git_cmd(["diff", "--name-only"]).splitlines()
        
    protected = policy.get("protected_paths", []) if policy else []
    violations = []
    
    for f in changed_files:
        if not f: continue
        for p in protected:
            if f.startswith(p.strip('/')):
                violations.append(f"Protected Path Modified: {f} (Requires L4 CodeOwner Review)")
                break
    return violations

def main():
    print("[T00 Meta-Audit] Starting Test-Integrity Verification...")
    
    policy = load_policy()
    if not policy:
        print("[WARNING] Could not load spec/guardrail_policy.yaml")
        
    violations = []
    
    # 1. FA-02 Test Deletion
    violations.extend(check_test_deletion())
    
    # 2. FA-01 Test Weakening (Skips/Xfails)
    violations.extend(check_test_weakening())
    
    # 3. FA-04 Manufactured Green
    violations.extend(check_manufactured_green())
        
    # 4. L4 Protected Paths (Tripwire)
    l4_violations = check_code_owner_violations(policy)
    if l4_violations:
        print("\n[WARNING] You are modifying L4 Protected Paths. These require manual review to merge.")
        for v in l4_violations:
            print(f" ⚠️ {v}")
        
    if violations:
        print("\n" + "="*60)
        print("T00 META-AUDIT FAILED - GUARDRAIL VIOLATIONS DETECTED")
        print("="*60)
        for v in violations:
            print(f" ❌ {v}")
        print("\nFix violations before proceeding.")
        sys.exit(1)
        
    print("[T00 Meta-Audit] All integrity checks passed. ✓")
    sys.exit(0)

if __name__ == "__main__":
    main()
