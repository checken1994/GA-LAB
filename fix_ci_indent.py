import re

filepath = '.github/workflows/scp-release-gate.yml'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '  SCP_JWT_SECRET: "dummy_secret_for_ci"\n',
    '        SCP_JWT_SECRET: "dummy_secret_for_ci"\n'
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
