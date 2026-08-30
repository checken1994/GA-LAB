import os
import re

downloads = r'C:\Users\check\Downloads'
for f in os.listdir(downloads):
    if f.endswith('.one'):
        print(f"Reading {f}")
        filepath = os.path.join(downloads, f)
        try:
            with open(filepath, 'rb') as file:
                data = file.read()
            # extract utf-16 strings because Windows/OneNote often uses UTF-16
            utf16_strings = re.findall(b'(?:[\\x20-\\x7E]\\x00){10,}', data)
            if utf16_strings:
                for s in utf16_strings:
                    print(s.decode('utf-16le', errors='ignore'))
            else:
                # fallback to ascii
                strings = re.findall(b'[a-zA-Z0-9 \\-.,_!:?/\\n]{10,}', data)
                for s in strings:
                    print(s.decode('ascii', errors='ignore'))
        except Exception as e:
            pass
