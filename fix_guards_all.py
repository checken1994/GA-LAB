import os
import glob
import re

def fix_guard(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove the lines that return early if is_local
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

for root, _, files in os.walk("."):
    for file in files:
        if file.endswith("_routes.py") or file == "chat.py" or file == "api_server.py":
            fix_guard(os.path.join(root, file))

