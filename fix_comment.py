import re

filepath = 'scp/runtime/multi_llm_crosscheck.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'  # \? FOR-LOOP.*?lại\n', '\n', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
