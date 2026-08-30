import os
import re

filepath = r'C:\Users\check\Downloads\Mục mới 5.one'
with open('output_notes5.txt', 'w', encoding='utf-8') as out:
    try:
        with open(filepath, 'rb') as file:
            data = file.read()
        
        # We can try to decode UTF-16 first
        utf16_strings = []
        for match in re.finditer(b'(?:[\\x20-\\x7E\\x80-\\xFF]\\x00){10,}', data):
            utf16_strings.append(match.group(0).decode('utf-16le', errors='ignore'))
        
        if utf16_strings:
            out.write("\n".join(utf16_strings))
        else:
            strings = re.findall(b'[a-zA-Z0-9 \\-.,_!:?/\\n]{10,}', data)
            out.write("\n".join([s.decode('ascii', errors='ignore') for s in strings]))
    except Exception as e:
        out.write(f"Error: {e}")
