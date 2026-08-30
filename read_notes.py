import os
import re

downloads = r'C:\Users\check\Downloads'
with open('output_notes.txt', 'w', encoding='utf-8') as out:
    for f in os.listdir(downloads):
        if f.endswith('.one') or f.endswith('.txt') or 'Note' in f:
            filepath = os.path.join(downloads, f)
            out.write(f"\n\n=== {f} ===\n")
            try:
                with open(filepath, 'rb') as file:
                    data = file.read()
                
                # We can try to decode UTF-16 first, OneNote strings often have \x00
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
