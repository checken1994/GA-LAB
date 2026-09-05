from scp.autofix.engine import AutoFixEngine
from pathlib import Path
from scp.autofix.bug_report_validator import validate_findings
from scp.autofix.runner_phases.ast_scan import _build_bug_report, _scan_file
from scp.autofix.runner_phases.post_fix_verify import run_full_post_fix_verify

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
target.write_text(GOOD_FIX_SOURCE, encoding="utf-8", newline="\n")
target.with_suffix(".py.tier3bak").write_text(BUGGY_SOURCE, encoding="utf-8", newline="\n")

print("Running post_fix_verify...")
res = run_full_post_fix_verify(
    bug_id="test",
    file_path=str(target),
    method_name="load_text",
    bug_type="BareExceptPass",
    run_vulture=True,
    run_import=True,
    run_hypothesis=False,
    run_reality_exercise=True,
    run_completeness=True,
    run_evidence_replay=True
)
import json
print(json.dumps(res, indent=2))
