import re

filepath = 'tests/test_provider_failover.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Just remove GroqProvider from imports everywhere in this file
content = content.replace(' GroqProvider,', '')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
