with open("scp/task_kernel.py", "r", encoding="utf-8") as f:
    text = f.read()

import re
text = re.sub(r'raise InvalidTransition\(f"WHY Gate crashed, fail-closed: \{why_err\}"\).*', 'raise InvalidTransition(f"WHY Gate crashed, fail-closed: {why_err}")', text)

with open("scp/task_kernel.py", "w", encoding="utf-8") as f:
    f.write(text)
