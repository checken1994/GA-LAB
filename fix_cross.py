import re

filepath = 'scp/runtime/multi_llm_crosscheck.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace tasks = [("primary", "judge")] with primary and secondary
content = re.sub(
    r'[ \t]*tasks = \[\("primary", "judge"\)\]',
    '    tasks = [("primary", "judge"), ("secondary", "autofix")]',
    content
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
