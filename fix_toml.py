filepath = 'scp/pyproject.toml'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('minversion = "9.0"', '')
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
