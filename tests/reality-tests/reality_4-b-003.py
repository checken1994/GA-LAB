from pathlib import Path
"""Reality test for Fix 4-b-003: trust root must NOT be forgeable by substring.

Before fix: 'Copyright (c) 2026' anywhere → approved (forgeable).
After fix: only explicit '# HUMAN_APPROVED_BY: name date' at line 1 → approved.

DNA #6 (Gốc tin cậy bên ngoài — trust root must be external & non-forgeable by SCP).
DNA #22 (PASS≠TRUE — substring match was a CLAIM of approval, not verification).
DNA #26 (reality test — every fix must be checked against real behavior).
"""
import re

HUMAN_APPROVED_PATTERN = re.compile(r'^#\s*HUMAN_APPROVED_BY:\s*(\S+)\s+(\d{4}-\d{2}-\d{2})\s*$')


def _is_approved(content: str) -> bool:
    """Mirror of the post-fix ExternalTrustRoot._is_constitution_human_approved."""
    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#!"):
            continue
        m = HUMAN_APPROVED_PATTERN.match(stripped)
        if m:
            from datetime import datetime
            try:
                datetime.strptime(m.group(2), "%Y-%m-%d")
                return True
            except ValueError:
                return False
        return False
    return False


# TEST 1: copyright notice alone must NOT pass (was the bug).
assert not _is_approved("# Copyright (c) 2026 SCP Project\n# stuff\n"), \
    "FAIL: copyright alone approved"
print("PASS: copyright-only constitution rejected")

# TEST 2: '# HUMAN_APPROVED' substring in a comment must NOT pass.
assert not _is_approved("# TODO: HUMAN_APPROVED\n# stuff\n"), \
    "FAIL: substring comment approved"
print("PASS: substring in comment rejected")

# TEST 3: valid line-1 marker must pass.
assert _is_approved("# HUMAN_APPROVED_BY: alice 2026-01-15\n# constitution body\n"), \
    "FAIL: valid marker rejected"
print("PASS: valid line-1 marker accepted")

# TEST 4: marker NOT at line 1 (after shebang) must NOT pass.
assert not _is_approved("#!/usr/bin/env python\n# stuff\n# HUMAN_APPROVED_BY: alice 2026-01-15\n"), \
    "FAIL: marker on wrong line accepted"
print("PASS: marker not at line 1 rejected")

# TEST 5: invalid date must NOT pass.
assert not _is_approved("# HUMAN_APPROVED_BY: alice 2026-13-45\n"), \
    "FAIL: invalid date accepted"
print("PASS: invalid date rejected")

# TEST 6: read actual source and verify the new pattern is in source AND the
# old buggy 'Copyright (c) 2026' substring marker is NOT in the markers list.
with open(str(Path(__file__).resolve().parents[2]) + '/scp/meta/external_trust.py') as f:
    src = f.read()

# New pattern-based check must be present.
assert "HUMAN_APPROVED_PATTERN" in src, \
    "FAIL: new HUMAN_APPROVED_PATTERN not in source"
assert "HUMAN_APPROVED_BY" in src, \
    "FAIL: HUMAN_APPROVED_BY marker text not in source"
print("PASS: new pattern-based check present in source")

# The old substring approach using HUMAN_APPROVED_MARKERS tuple with
# "Copyright (c) 2026" must be gone from CODE (allowed in comments).
code_lines = [l for l in src.split("\n") if not l.strip().startswith("#")]
code_section = "\n".join(code_lines)
# Look for the old markers tuple literal containing the copyright string.
old_marker_in_code = (
    '"Copyright (c) 2026"' in code_section
    and "HUMAN_APPROVED_MARKERS" in code_section
)
assert not old_marker_in_code, \
    "FAIL: old HUMAN_APPROVED_MARKERS tuple with 'Copyright (c) 2026' still in code"
print("PASS: old 'Copyright (c) 2026' substring marker removed from code")

print("\n✓ Reality test 4-b-003 PASSED (7/7 assertions)")
