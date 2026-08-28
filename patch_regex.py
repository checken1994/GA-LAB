import re
with open(r"c:\Users\check\Downloads\scp\scp\ask_kernel_adapter.py", "r", encoding="utf-8") as f:
    text = f.read()

text = re.sub(r'return set\(re\.findall\(r"\[.*?\]\{4,\}", \(text or ""\)\.lower\(\)\)\)', 'return set(re.findall(r"[\\\\w\\\\u00C0-\\\\u1EF9]+|\\\\d+", (text or "").lower()))', text)

with open(r"c:\Users\check\Downloads\scp\scp\ask_kernel_adapter.py", "w", encoding="utf-8") as f:
    f.write(text)
