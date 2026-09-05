#!/usr/bin/env python3
"""SCP T03 Evidence Authority (FA-03)

Implements the Producer and Validator for cryptographically tied test evidence.
Guarantees that a PASS/VERIFIED claim is backed by exact-SHA, tree-equivalent,
and untampered output logs.
"""
import sys
import json
import hashlib
import subprocess
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def run_git(args, cwd=PROJECT_ROOT) -> str:
    res = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd)
    if res.returncode != 0:
        raise RuntimeError(f"Git command failed: {' '.join(args)}\n{res.stderr}")
    return res.stdout.strip()

def get_git_state() -> Tuple[str, str, bool]:
    sha = run_git(["rev-parse", "HEAD"])
    tree = run_git(["rev-parse", "HEAD^{tree}"])
    status = run_git(["status", "--porcelain"])
    is_clean = len(status) == 0
    return sha, tree, is_clean

class EvidenceProducer:
    def __init__(self, profile: Dict[str, Any]):
        self.profile = profile

    def _hash_profile(self) -> str:
        s = json.dumps(self.profile, sort_keys=True)
        return hashlib.sha256(s.encode('utf-8')).hexdigest()

    def _hash_output(self, stdout: str, stderr: str) -> str:
        return hashlib.sha256((stdout + stderr).encode('utf-8')).hexdigest()

    def produce(self) -> Dict[str, Any]:
        sha, tree, is_clean = get_git_state()
        clean_req = self.profile.get("clean_required", True)
        
        if clean_req and not is_clean:
            # We can still produce evidence, but the validator will reject it if clean is required.
            pass

        started_at = datetime.utcnow().isoformat() + "Z"
        
        # Run the commands
        combined_stdout = ""
        combined_stderr = ""
        exit_code = 0
        
        for cmd in self.profile.get("commands", []):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
                combined_stdout += res.stdout
                combined_stderr += res.stderr
                if res.returncode != 0:
                    exit_code = res.returncode
                    break
            except Exception as e:
                combined_stderr += str(e)
                exit_code = 127
                break
                
        finished_at = datetime.utcnow().isoformat() + "Z"
        
        evidence = {
            "schema_version": "1.0",
            "tested_sha": sha,
            "tree_hash": tree,
            "git_clean": is_clean,
            "test_profile_hash": self._hash_profile(),
            "exit_code": exit_code,
            "started_at": started_at,
            "finished_at": finished_at,
            "output_hash": self._hash_output(combined_stdout, combined_stderr),
            "profile": self.profile, # Store profile for transparency
            "stdout": combined_stdout, # Stored for CI debugging, not strict for hashing if hash matches
            "stderr": combined_stderr
        }
        
        return evidence

class EvidenceValidator:
    REQUIRED_FIELDS = {
        "tested_sha", "tree_hash", "git_clean", "test_profile_hash", 
        "exit_code", "started_at", "finished_at", "output_hash"
    }

    def __init__(self, expected_sha: str = None):
        self.expected_sha = expected_sha

    def validate(self, evidence: Dict[str, Any]) -> Tuple[bool, str]:
        # 1. Missing fields
        missing = self.REQUIRED_FIELDS - set(evidence.keys())
        if missing:
            return False, f"Missing required fields: {missing}"

        # 2. Exit code
        if evidence["exit_code"] != 0:
            return False, f"Evidence reports non-zero exit code: {evidence['exit_code']}"

        # 3. Temporal sanity
        try:
            start = datetime.fromisoformat(evidence["started_at"].replace("Z", ""))
            end = datetime.fromisoformat(evidence["finished_at"].replace("Z", ""))
            if start > end:
                return False, "started_at is after finished_at"
        except ValueError:
            return False, "Invalid timestamp format"

        # 4. Hash integrity
        profile_hash = hashlib.sha256(json.dumps(evidence.get("profile", {}), sort_keys=True).encode()).hexdigest()
        if profile_hash != evidence["test_profile_hash"]:
            return False, "Test profile hash mismatch (profile modified)"

        out_hash = hashlib.sha256((evidence.get("stdout", "") + evidence.get("stderr", "")).encode()).hexdigest()
        if out_hash != evidence["output_hash"]:
            return False, "Output hash mismatch (logs tampered)"

        # 5. Git state matching
        current_sha, current_tree, current_clean = get_git_state()
        
        # Blocker 1: Anti-Spoofing
        if self.expected_sha and self.expected_sha != current_sha:
            return False, f"Spoofed SHA: expected_sha ({self.expected_sha}) does not match current system HEAD ({current_sha})"
            
        if evidence["tested_sha"] != current_sha:
            return False, f"SHA mismatch: evidence for {evidence['tested_sha']}, current system HEAD is {current_sha}"
            
        if evidence["tree_hash"] != current_tree:
            return False, f"Tree mismatch: evidence tree {evidence['tree_hash']}, current {current_tree}"

        # Blocker 2: Post-verification dirty state
        req_clean = evidence.get("profile", {}).get("clean_required", True)
        if req_clean:
            if not evidence.get("git_clean", False):
                return False, "Evidence was generated on a dirty working tree"
            if not current_clean:
                return False, "Current working tree is dirty (post-verification state is not clean)"

        return True, "VERIFIED"

def main():
    parser = argparse.ArgumentParser(description="SCP T03 Evidence Authority")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Produce
    prod_parser = subparsers.add_parser("produce")
    prod_parser.add_argument("--out", type=str, default=".evidence.json")
    
    # Validate
    val_parser = subparsers.add_parser("validate")
    val_parser.add_argument("--in-file", type=str, dest="in_file", default=".evidence.json")
    val_parser.add_argument("--candidate-sha", type=str, default=None)

    args = parser.parse_args()
    
    if args.command == "produce":
        profile = {
            "name": "SCP Core Tests",
            "clean_required": True,
            "commands": [
                [sys.executable, "-m", "pytest", "tests/", "-q"]
            ]
        }
        producer = EvidenceProducer(profile)
        evidence = producer.produce()
        
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, indent=2))
        print(f"Evidence produced and written to {args.out}")
        sys.exit(0 if evidence["exit_code"] == 0 else evidence["exit_code"])

    elif args.command == "validate":
        ev_path = Path(args.in_file)
        if not ev_path.exists():
            print(f"Evidence file {args.in_file} not found.")
            sys.exit(1)
            
        evidence = json.loads(ev_path.read_text())
        validator = EvidenceValidator(expected_sha=args.candidate_sha)
        ok, msg = validator.validate(evidence)
        
        if ok:
            print(f"[FA-03] {msg}")
            sys.exit(0)
        else:
            print(f"[FA-03] DENY: {msg}")
            sys.exit(1)

if __name__ == "__main__":
    main()
