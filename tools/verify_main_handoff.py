#!/usr/bin/env python3
"""Require immutable merged-PR lineage before a fresh main handoff verdict."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


def validate_lineage(sha: str, expected: str, remote: str, parents: list[str],
                     pulls: list[dict], event: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or remote != sha:
        raise ValueError("checkout SHA must equal live main SHA")
    if event not in {"push", "workflow_dispatch"}:
        raise ValueError("unsupported main handoff event")
    if event == "workflow_dispatch" and expected != sha:
        raise ValueError("dispatch must name the exact main merge SHA")
    if len(parents) != 2:
        raise ValueError("customer handoff requires a two-parent RC merge commit")
    matches = [pr for pr in pulls if pr.get("merged_at")
               and pr.get("merge_commit_sha") == sha
               and pr.get("base", {}).get("ref") == "main"
               and pr.get("head", {}).get("sha") == parents[1]
               and pr.get("head", {}).get("ref") == "integration/experiment-god-split-and-providers"]
    if len(matches) != 1:
        raise ValueError("exactly one merged integration PR must match main and frozen parent SHA")
    return {"status": "PASS_WITHIN_SCOPE", "main_sha": sha, "frozen_sha": parents[1],
            "pr": matches[0]["number"], "event": event}


def main() -> int:
    def read(*command: str) -> str:
        return subprocess.check_output(list(command), text=True, encoding="utf-8").strip()

    sha = os.environ["GITHUB_SHA"]
    if read("git", "rev-parse", "HEAD") != sha:
        raise ValueError("working checkout does not match GITHUB_SHA")
    repo = os.environ["GITHUB_REPOSITORY"]
    remote = read("gh", "api", f"repos/{repo}/git/ref/heads/main", "--jq", ".object.sha")
    parents = [line.split()[1] for line in read("git", "cat-file", "-p", "HEAD").splitlines()
               if line.startswith("parent ")]
    pages = json.loads(read("gh", "api", f"repos/{repo}/commits/{sha}/pulls", "--paginate", "--slurp"))
    evidence = validate_lineage(sha, os.environ.get("HANDOFF_MERGE_SHA", ""), remote,
                                parents, [pr for page in pages for pr in page],
                                os.environ["GITHUB_EVENT_NAME"])
    output = Path("reports/release/main-lineage.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
