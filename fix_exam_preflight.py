import re

with open("benchmark/run_world_exam.py", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace(
    'req = urllib.request.Request("http://127.0.0.1:8002/ask", data=body, headers={\'Content-Type\': \'application/json\', \'Authorization\': f\'Bearer {token}\'}, method="POST")',
    'req = urllib.request.Request("http://127.0.0.1:8002/docs", method="GET")'
, 1) # Only replace the first occurrence (in pre-flight check)

with open("benchmark/run_world_exam.py", "w", encoding="utf-8") as f:
    f.write(text)
