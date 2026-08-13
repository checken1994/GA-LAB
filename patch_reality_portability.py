from pathlib import Path
from datetime import datetime
import re

ROOT = Path.cwd()
TEST_DIR = ROOT / "tests" / "reality-tests"
if not TEST_DIR.exists():
    raise SystemExit(f"missing {TEST_DIR}")
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP = ROOT / ".private-secrets" / f"reality-tests-before-portability-{STAMP}"
BACKUP.mkdir(parents=True, exist_ok=True)
OLD = "/home/z/my-project/scp-system"
ROOT_EXPR = "str(Path(__file__).resolve().parents[2])"
changed = []
for path in sorted(TEST_DIR.rglob("*.py")):
    text = path.read_text(encoding="utf-8-sig")
    if OLD not in text:
        continue
    rel = path.relative_to(ROOT)
    backup = BACKUP / rel
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(path.read_bytes())
    def repl(match: re.Match[str]) -> str:
        suffix = match.group(2)
        return ROOT_EXPR + (repr(suffix) if suffix else "")
    # Replace only occurrences inside quoted Python string literals.
    new, count = re.subn(r"(['\"])" + re.escape(OLD) + r"([^'\"]*)\1", repl, text)
    if count == 0:
        raise SystemExit(f"literal marker not replaced in {path}")
    if "from pathlib import Path" not in new:
        lines = new.splitlines(keepends=True)
        insert_at = 0
        while insert_at < len(lines) and (lines[insert_at].startswith("#!") or "coding" in lines[insert_at]):
            insert_at += 1
        future = [i for i, line in enumerate(lines) if line.startswith("from __future__ import ")]
        if future:
            insert_at = max(future) + 1
        lines.insert(insert_at, "from pathlib import Path\n")
        new = "".join(lines)
    path.write_text(new, encoding="utf-8", newline="\n")
    changed.append((str(rel), count))
print(f"changed_files={len(changed)}")
print(f"replacements={sum(c for _, c in changed)}")
print(f"backup={BACKUP}")
for name, count in changed:
    print(f"{name}: {count}")
