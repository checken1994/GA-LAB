#!/usr/bin/env python3
"""Verify a committed snapshot manifest against Git, not report self-claims."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def inventory(commit: str) -> list[dict[str, str]]:
    raw = subprocess.check_output(["git", "ls-tree", "-r", "-z", commit], encoding=None)
    rows: list[dict[str, str]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, path = item.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split(" ", 2)
        rows.append({"mode": mode, "type": kind, "blob": oid, "path": path.decode("utf-8")})
    return sorted(rows, key=lambda row: row["path"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest: dict[str, Any] = json.loads(args.manifest.read_text(encoding="utf-8"))
    captured = str(manifest["captured_commit"])
    current = git("rev-parse", "HEAD")
    if current != captured:
        parents = git("rev-list", "--parents", "-n", "1", current).split()[1:]
        if captured not in parents:
            raise SystemExit(f"manifest captured commit is not HEAD or its direct parent: {captured} vs {current}")
    rows = inventory(captured)
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    actual_sha = hashlib.sha256(canonical).hexdigest()
    if len(rows) != int(manifest["tracked_count"]):
        raise SystemExit(f"tracked count mismatch: {len(rows)} != {manifest['tracked_count']}")
    if actual_sha != manifest["inventory_sha256"]:
        raise SystemExit("tracked inventory hash mismatch")
    actual_tree = git("rev-parse", f"{captured}^{{tree}}")
    if actual_tree != manifest["captured_tree"]:
        raise SystemExit("captured tree SHA mismatch")
    by_path = {row["path"]: row for row in rows}
    for path, expected in manifest["required_paths"].items():
        if path not in by_path or by_path[path]["blob"] != expected["blob"]:
            raise SystemExit(f"required path/blob mismatch: {path}")
        data = subprocess.check_output(["git", "show", f"{captured}:{path}"], encoding=None)
        if len(data) != int(expected["bytes"]) or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise SystemExit(f"required path content hash mismatch: {path}")
    print(json.dumps({"status": "PASS_WITHIN_SCOPE", "captured_commit": captured, "current_head": current, "tracked_count": len(rows), "tree": actual_tree}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
