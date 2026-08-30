import os
import shutil
import subprocess

def run_speculative_branching(patch_candidates: list[str], target_file: str):
    # Cơ chế Speculative Branching: chạy đua N giải pháp trong N container tạm
    best_patch = None
    best_rc = 1
    
    for i, patch in enumerate(patch_candidates):
        backup = target_file + f".branch{i}.bak"
        shutil.copy(target_file, backup)
        try:
            with open(target_file, "w") as f:
                f.write(patch)
            
            # Chạy tests trên nhánh spec
            result = subprocess.run(["pytest", "-q"], capture_output=True)
            if result.returncode == 0:
                best_patch = patch
                best_rc = 0
                break # Found a passing patch
        finally:
            shutil.copy(backup, target_file)
            os.remove(backup)
            
    if best_rc == 0:
        with open(target_file, "w") as f:
            f.write(best_patch)
        return True
    return False
