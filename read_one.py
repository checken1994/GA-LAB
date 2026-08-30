import os

filepath = r'C:\Users\check\Downloads\Mục Mới 1.one'
try:
    with open(filepath, 'rb') as f:
        data = f.read()
    # Extract readable strings
    import re
    strings = re.findall(b'[a-zA-Z0-9 \\-.,_!:?/\\n]{10,}', data)
    print("=== Mục Mới 1.one ===")
    for s in strings:
        print(s.decode('ascii', errors='ignore'))
except Exception as e:
    print(f"Error reading {filepath}: {e}")
