import urllib.request
import json
from scp.security.jwt_guard import create_access_token

token = create_access_token({"sub": "admin"})
print(f"Generated Token: {token}")

url = "http://127.0.0.1:8002/ask"
req = urllib.request.Request(url, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", f"Bearer {token}")
data = json.dumps({"question": "test", "session_id": "test"}).encode("utf-8")

try:
    with urllib.request.urlopen(req, data=data) as response:
        print(f"Status: {response.status}")
        print(response.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print(f"Error Status: {e.code}")
    print(e.read().decode("utf-8"))
