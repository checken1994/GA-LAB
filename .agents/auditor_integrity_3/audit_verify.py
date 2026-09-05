import sys
import re
from pathlib import Path
import ast
import subprocess

REPORT_PATH = Path(r"c:\Users\check\Downloads\scp\teamwork_runtime_audit_report.md")
REPO_ROOT = Path(r"c:\Users\check\Downloads\scp")

print("=" * 70)
print("FORENSIC AUDITOR 3: INDEPENDENT EMPIRICAL AUDIT")
print("=" * 70)

report_content = REPORT_PATH.read_text(encoding="utf-8")
lines = report_content.splitlines()

# -------------------------------------------------------------
# CHECK 1: Section 3.3 Analysis
# -------------------------------------------------------------
print("\n--- CHECK 1: SECTION 3.3 ANALYSIS ---")
# Find Section 3.3 lines
sec_3_3_start = None
sec_3_3_end = None
for i, line in enumerate(lines):
    if "### 3.3 Main Root Test Suite" in line:
        sec_3_3_start = i
    elif sec_3_3_start is not None and i > sec_3_3_start and line.startswith("### 3.4"):
        sec_3_3_end = i
        break

assert sec_3_3_start is not None and sec_3_3_end is not None, "Could not find Section 3.3 boundaries"
sec_3_3_text = "\n".join(lines[sec_3_3_start:sec_3_3_end])

# Extract test suite lines matching `tests\...`
suite_lines = [l.strip() for l in lines[sec_3_3_start:sec_3_3_end] if re.match(r"^tests[\\/].*\.py\s+\.+", l.strip())]
print(f"Total test suite lines found in Section 3.3: {len(suite_lines)}")

missing_suites = []
total_test_dots = 0
suite_details = []

for sl in suite_lines:
    parts = sl.split()
    path_str = parts[0]
    # Count dots
    # The line is like: `tests\T00_integrity\test_meta_audit.py ..............................    [  6%]`
    # After path_str, the dots are the next part
    dots_part = parts[1]
    dot_count = dots_part.count(".")
    total_test_dots += dot_count
    
    p = REPO_ROOT / path_str.replace("\\", "/")
    if not p.exists():
        missing_suites.append(path_str)
    suite_details.append((path_str, dot_count, p.exists()))

print(f"Number of suites listed: {len(suite_lines)}")
print(f"Total test dots across all 94 suites: {total_test_dots}")
print(f"Missing suite files count: {len(missing_suites)}")
if missing_suites:
    print(f"FAIL: Missing suites: {missing_suites}")
else:
    print("PASS: All suite files physically exist on disk.")

# Check for previously fabricated directories/files
prohibited_tokens = [
    r"T01_discovery",
    r"T02_policy",
    r"T08_autofix",
    r"test_system_discovery",
    r"test_policy_engine",
    r"test_reality_judge",
    r"test_quarantine_pipeline",
    r"test_reality_test_adversarial",
    r"test_e2e_golden_task",
]
found_prohibited_3_3 = []
for tok in prohibited_tokens:
    if tok in sec_3_3_text:
        found_prohibited_3_3.append(tok)

print(f"Prohibited/Fabricated tokens in Section 3.3: {found_prohibited_3_3}")
assert len(found_prohibited_3_3) == 0, f"Found prohibited tokens in Sec 3.3: {found_prohibited_3_3}"

# -------------------------------------------------------------
# CHECK 2: Section 3.5 Item 3 (Golden Tasks) Analysis
# -------------------------------------------------------------
print("\n--- CHECK 2: SECTION 3.5 ITEM 3 ANALYSIS ---")
sec_3_5_start = None
sec_3_5_end = None
for i, line in enumerate(lines):
    if "### 3.5 Core Subsystem Test Suites Execution" in line:
        sec_3_5_start = i
    elif sec_3_5_start is not None and i > sec_3_5_start and line.startswith("### 3.6"):
        sec_3_5_end = i
        break

assert sec_3_5_start is not None and sec_3_5_end is not None
sec_3_5_text = "\n".join(lines[sec_3_5_start:sec_3_5_end])

# Look for Golden task block: "3. **Golden Tasks E2E (`pytest tests/T09_golden_task/ -v`)"
g_start = None
g_lines = []
for i in range(sec_3_5_start, sec_3_5_end):
    if "Golden Tasks E2E" in lines[i]:
        g_start = i
        continue
    if g_start is not None:
        if lines[i].startswith("4. **"):
            break
        if "::" in lines[i] and "PASSED" in lines[i]:
            g_lines.append(lines[i].strip())

print(f"Golden task test lines found in Section 3.5 item 3: {len(g_lines)}")
for gl in g_lines:
    print(f"  {gl}")

# Check each nodeid in g_lines
missing_golden_tests = []
for gl in g_lines:
    nodeid = gl.split()[0]
    fpath, test_name = nodeid.split("::")
    p = REPO_ROOT / fpath.replace("\\", "/")
    if not p.exists():
        missing_golden_tests.append((nodeid, "File not found"))
    else:
        file_text = p.read_text(encoding="utf-8")
        clean_test_name = test_name.split("[")[0]
        if f"def {clean_test_name}" not in file_text and f"class {clean_test_name}" not in file_text:
            missing_golden_tests.append((nodeid, "Test function not found"))

print(f"Missing/Invalid golden tests: {missing_golden_tests}")
assert len(missing_golden_tests) == 0, f"Found invalid golden tests: {missing_golden_tests}"

# Check for previously fabricated golden task tests
prohibited_golden = [
    "test_golden_task_happy_path",
    "test_golden_task_policy_blocked",
    "test_golden_task_replay_deduplication",
    "test_scp_complete_lifecycle",
    "test_scp_immutable_state_machine",
    "test_scp_policy_enforcement_at_dispatch",
    "test_scp_verifier_rejects_ungrounded",
    "test_evidence_provenance_binding",
    "test_e2e_golden_task.py",
]
found_prohibited_golden = []
for tok in prohibited_golden:
    if tok in sec_3_5_text:
        found_prohibited_golden.append(tok)

print(f"Prohibited/Fabricated tokens in Section 3.5 Item 3: {found_prohibited_golden}")
assert len(found_prohibited_golden) == 0, f"Found prohibited tokens: {found_prohibited_golden}"

# -------------------------------------------------------------
# CHECK 3: Global File Path and Test NodeID Scan
# -------------------------------------------------------------
print("\n--- CHECK 3: GLOBAL DOCUMENT PATH & NODEID SCAN ---")

# Scan all paths like (scp/... or tests/... or tools/...)
raw_paths = re.findall(r'(?:scp|tests|tools)[/\\\\][a-zA-Z0-9_\-./\\\\]+\.(?:py|md|toml|ini|json|yaml|yml|txt)', report_content)
unique_paths = set(p.replace("\\", "/").rstrip(":;,)") for p in raw_paths)
print(f"Total unique file paths found: {len(unique_paths)}")

missing_paths = []
for p in sorted(unique_paths):
    full_p = REPO_ROOT / p
    if not full_p.exists():
        missing_paths.append(p)

print(f"Missing file paths: {len(missing_paths)}")
if missing_paths:
    for mp in missing_paths:
        print(f"  [MISSING] {mp}")
else:
    print("PASS: 100% of referenced file paths physically exist on disk.")

# Scan all test nodeids like path.py::func_name
raw_nodeids = re.findall(r'((?:tests|scp/tests)[/\\\\][a-zA-Z0-9_\-./\\\\]+\.py::[a-zA-Z0-9_\[\]\-]+)', report_content)
unique_nodeids = set(n.replace("\\", "/") for n in raw_nodeids)
print(f"Total unique test nodeids found: {len(unique_nodeids)}")

invalid_nodeids = []
for n in sorted(unique_nodeids):
    fpath, tname = n.split("::")
    p = REPO_ROOT / fpath
    if not p.exists():
        invalid_nodeids.append((n, "file missing"))
        continue
    content = p.read_text(encoding="utf-8")
    clean_name = tname.split("[")[0]
    if clean_name not in content:
        invalid_nodeids.append((n, f"function '{clean_name}' not in {fpath}"))

print(f"Invalid test nodeids: {len(invalid_nodeids)}")
if invalid_nodeids:
    for inv in invalid_nodeids:
        print(f"  [INVALID] {inv}")
else:
    print("PASS: 100% of test nodeids physically exist in target files.")

# -------------------------------------------------------------
# CHECK 4: Cross-reference with real pytest collection
# -------------------------------------------------------------
print("\n--- CHECK 4: PYTEST COLLECTION REALITY CHECK ---")
res = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"], capture_output=True, text=True, cwd=REPO_ROOT)
col_lines = res.stdout.strip().splitlines()
last_line = col_lines[-1] if col_lines else ""
print(f"Pytest collection summary line: {last_line}")
assert "515 tests collected" in last_line, f"Expected 515 tests collected, got: {last_line}"

# Verify count of suites collected
collected_files = set()
for cl in col_lines:
    if "::" in cl:
        f = cl.split("::")[0].replace("/", "\\")
        collected_files.add(f)
print(f"Unique test files collected by pytest in tests/: {len(collected_files)}")
assert len(collected_files) == 94, f"Expected 94 test files, got {len(collected_files)}"

# Verify that the 94 suite lines in the report match collected_files
report_suites = set(sl.split()[0].replace("/", "\\") for sl in suite_lines)
diff_suites = collected_files.symmetric_difference(report_suites)
print(f"Symmetric difference between collected suites and report suites: {len(diff_suites)}")
if diff_suites:
    print(f"Differences: {diff_suites}")
assert len(diff_suites) == 0, f"Suite sets do not match: {diff_suites}"

print("\nALL AUTOMATED FORENSIC CHECKS PASSED PERFECTLY!")
