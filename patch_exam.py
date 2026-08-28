import re

with open("benchmark/run_world_exam.py", "r", encoding="utf-8") as f:
    text = f.read()

# Generate token and inject header
imports = "import urllib.request\nfrom scp.security.jwt_guard import create_access_token\n"
text = text.replace("import urllib.request", imports, 1)

header_injection = """        token = create_access_token({"sub": "benchmark-runner"})
        req = urllib.request.Request("http://127.0.0.1:8002/ask", data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}, method="POST")"""

text = re.sub(r'req = urllib\.request\.Request\("http://127\.0\.0\.1:8002/ask", data=body, headers=\{\'Content-Type\': \'application/json\'\}, method="POST"\)', header_injection, text)

with open("benchmark/run_world_exam.py", "w", encoding="utf-8") as f:
    f.write(text)
