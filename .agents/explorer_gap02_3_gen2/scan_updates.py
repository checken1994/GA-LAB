import sys
import re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

repo_root = Path(__file__).resolve().parents[2]
scp_dir = repo_root / "scp"

print(f"Scanning scp directory: {scp_dir}")

for p in sorted(scp_dir.rglob("*.py")):
    text = p.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if "UPDATE " in line.upper():
            # grab up to 4 lines for multi-line SQL
            snippet = " ".join(l.strip() for l in lines[i-1:min(len(lines), i+4)])
            m = re.search(r'UPDATE\s+([a-zA-Z0-9_]+)\s+SET\s+(.*?)(?:WHERE\s+([^\"\';]+))?', snippet, re.IGNORECASE)
            if m:
                table = m.group(1)
                sets = m.group(2).strip()
                where = (m.group(3) or "").strip()
                has_ver = "version" in where.lower()
                rel_path = p.relative_to(repo_root)
                print(f"{rel_path}:{i} | TABLE: {table} | WHERE: {where} | OCC: {has_ver}")
