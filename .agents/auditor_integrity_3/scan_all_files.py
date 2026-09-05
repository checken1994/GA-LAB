from pathlib import Path
import re

text = Path(r"c:\Users\check\Downloads\scp\teamwork_runtime_audit_report.md").read_text(encoding="utf-8")
repo_root = Path(r"c:\Users\check\Downloads\scp")

paths = re.findall(r'[\w\-./\\]+\.(?:py|toml|ini|json|yaml|yml|md)', text)
repo_files = set()
for p in paths:
    p_norm = p.replace('\\', '/').rstrip('.:;,)\'"]')
    for prefix in ['scp/', 'tests/', 'tools/', '.agents/', '.github/', 'spec/']:
        if p_norm.startswith(prefix):
            repo_files.add(p_norm)

missing = []
for f in sorted(repo_files):
    if not (repo_root / f).exists():
        missing.append(f)

print(f"Total repo file references (including .agents, .github, spec, scp, tests, tools): {len(repo_files)}")
print(f"Missing count: {len(missing)}")
if missing:
    for m in missing:
        print(f"  Missing: {m}")
else:
    print("PASS: 100% of repo files exist!")
