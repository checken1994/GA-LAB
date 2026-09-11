"""Speculative branching: race N patch candidates against the test suite.

[S3-SECURITY-SWEEP] Hardening (HIGH path-traversal fix): the target file
flows into copy/write sinks, so it is validated (no parent-directory
components, must be an existing file) and resolved to an absolute path
before use. The per-branch backup name is derived from the resolved target,
so no traversal is possible through the backup path either.
"""
import os
import shutil
import subprocess
from pathlib import Path

def run_speculative_branching(patch_candidates: list[str], target_file: str):
    # Cơ chế Speculative Branching: chạy đua N giải pháp trong N container tạm
    # [S3-SECURITY-SWEEP] validate + resolve target before any write.
    target = Path(target_file)
    if ".." in target.parts:
        raise ValueError(
            f"target_file contains traversal components: {target_file!r}"
        )
    if not target.is_file():
        raise ValueError(f"target_file does not exist: {target_file!r}")
    resolved_target = target.resolve()
    best_patch = None
    best_rc = 1

    for i, patch in enumerate(patch_candidates):
        backup = str(resolved_target) + f".branch{i}.bak"
        shutil.copy(str(resolved_target), backup)
        try:
            with resolved_target.open("w") as f:
                f.write(patch)

            # Chạy tests trên nhánh spec
            result = subprocess.run(["pytest", "-q"], capture_output=True)
            if result.returncode == 0:
                best_patch = patch
                best_rc = 0
                break # Found a passing patch
        finally:
            shutil.copy(backup, str(resolved_target))
            os.remove(backup)

    if best_rc == 0:
        with resolved_target.open("w") as f:
            f.write(best_patch)
        return True
    return False
