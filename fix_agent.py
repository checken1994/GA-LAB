import re

filepath = 'scp/api/routes/agent_routes.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

new_content = re.sub(
    r'[ \t]*# Fallback: local-only mode.*?\n[ \t]*host = request.*?if local_only and host in.*?return\n',
    '',
    content,
    flags=re.MULTILINE | re.DOTALL
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Fixed agent_routes.py")
