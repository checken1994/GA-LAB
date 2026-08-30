import os
import glob

def fix_guard(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We want to remove the lines that return early if is_local
    # Pattern is generally:
    # if is_local and os.environ.get("SCP_...", "1") == "1" and not request.headers.get("X-Forwarded-For"):
    #     return
    import re
    new_content = re.sub(
        r'^[ \t]*if\s+(?:is_local|_is_local\(request\))\s+and\s+os\.environ\.get\([^)]+\)\s+==\s+"1"\s+and\s+not\s+request\.headers\.get\("X-Forwarded-For"\):\n[ \t]*return\n',
        '',
        content,
        flags=re.MULTILINE
    )
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed {filepath}")

for f in glob.glob("scp/api/routes/*_routes.py"):
    fix_guard(f)

