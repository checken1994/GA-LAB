from scp.autofix.engine import AutoFixEngine
from pathlib import Path
from scp.autofix.bug_report_validator import validate_findings
from scp.autofix.runner_phases.ast_scan import _build_bug_report, _scan_file

BUGGY_SOURCE = (
    "def load_text(path):\n"
    "    try:\n"
    "        with open(path, encoding=\"utf-8\") as handle:\n"
    "            return handle.read()\n"
    "    except:\n"
    "        pass\n"
)
GOOD_FIX_SOURCE = (
    "def load_text(path):\n"
    "    try:\n"
    "        with open(path, encoding=\"utf-8\") as handle:\n"
    "            return handle.read()\n"
    "    except OSError:\n"
    "        return \"\"\n"
)

workspace = Path("C:/Users/check/Downloads/scp/tmp_workspace")
workspace.mkdir(exist_ok=True)
target = workspace / "util.py"
target.write_text(BUGGY_SOURCE, encoding="utf-8", newline="\n")

# To satisfy _verify_fix's need for a backup file:
target.with_suffix(".py.tier3bak").write_text(BUGGY_SOURCE, encoding="utf-8", newline="\n")

findings = _scan_file(target)
reports = [_build_bug_report(str(target), f) for f in findings]
validated = validate_findings(reports)
bug = next(b for b in validated if b.bug_type == "BareExceptPass")

target.write_text(GOOD_FIX_SOURCE, encoding="utf-8", newline="\n")

engine = AutoFixEngine("C:/Users/check/Downloads/scp/tmp_data")
print("Running verify...")
ok, reason = engine._verify_fix(target, [bug])
print(f"ok: {ok}")
print(f"reason: {reason}")
