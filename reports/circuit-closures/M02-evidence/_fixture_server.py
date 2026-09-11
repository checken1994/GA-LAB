# M2 D3 runtime fixture: local OpenAI-compat answer source (same shape as the
# D1 contract-test fixture in tests/T02_contract/test_flow_02). Judge prompts
# (containing "PASS or FAIL") get "PASS"; chat prompts get a fixed answer.
# Runs INSIDE the temporary standard-profile container on 127.0.0.1:9101.
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages", [])
        is_judge_prompt = any(
            "PASS or FAIL" in str(m.get("content", "")) for m in messages
        )
        content = (
            "PASS"
            if is_judge_prompt
            else "Đáp án fixture cục bộ: 2 cộng 2 bằng 4."
        )
        payload = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": content}}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 9101), Handler).serve_forever()
