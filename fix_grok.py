import re

filepath = 'scp/web_control/ai_orchestrator.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'[ \t]*"grok": "https://grok\.com/",\n', '', content)
content = re.sub(r'[ \t]*"grok": \("grok\.com", "x\.com"\),\n', '', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

filepath = 'scp/web_control/multi_source_orchestrator.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(', "grok"', '')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
