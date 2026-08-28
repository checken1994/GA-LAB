import re
with open("benchmark/run_world_exam.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip().startswith("token = create_access_token"):
        new_lines.append("        token = create_access_token({\"sub\": \"benchmark-runner\"})\n")
    elif line.strip().startswith("req = urllib.request.Request"):
        new_lines.append("        req = urllib.request.Request(\"http://127.0.0.1:8002/ask\", data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}, method=\"POST\")\n")
    else:
        new_lines.append(line)

with open("benchmark/run_world_exam.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
