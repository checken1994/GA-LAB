filepath = 'scp/requirements.txt'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('PyJWT==2.10.1', 'PyJWT>=2.13.0')
content = content.replace('pyjwt==2.10.1', 'pyjwt>=2.13.0')
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
