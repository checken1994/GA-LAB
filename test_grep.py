import os
import glob
for file in glob.glob('scp/**/*.py', recursive=True):
    with open(file, 'r', encoding='utf-8') as f:
        try:
            content = f.read()
            if 'decision == "REJECT"' in content or 'decision == "ALLOW"' in content or 'why_res.decision' in content:
                print(f"FOUND IN: {file}")
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'decision == ' in line or 'why_res' in line:
                        print(f"  Line {i+1}: {line.strip()}")
        except Exception:
            pass
