import re

filepath = 'tests/test_xff_guard_contract.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('result = guard_fn(req_local, None)', 'result = guard_fn(req_local, "test_token")')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
