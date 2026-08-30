import re

for filepath in [
    'data/diagnostics/agent-autofix-staging/agent_routes.py',
    'data/diagnostics/agent-orchestrator-staging/agent_routes.py'
]:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        new_content = re.sub(
            r'[ \t]*host = request.*?if local_only and host in.*?return\n',
            '',
            content,
            flags=re.MULTILINE | re.DOTALL
        )

        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Fixed {filepath}")
    except FileNotFoundError:
        pass
