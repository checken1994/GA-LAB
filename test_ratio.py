import re
def _terms(text):
    return set(re.findall(r"[\w\u00C0-\u1EF9]+|\d+", (text or "").lower()))

ans = _terms("72")
ctx = _terms("The verified answer is exactly 72")
print("ANS:", ans)
print("CTX:", ctx)
print("INTERSECTION:", ans & ctx)
print("RATIO:", len(ans & ctx) / max(1, len(ans)))
