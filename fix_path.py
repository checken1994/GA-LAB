import sys
import os
import re

with open("benchmark/run_world_exam.py", "r", encoding="utf-8") as f:
    text = f.read()

import_sys = "import sys\nimport os\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))\nfrom scp.security.jwt_guard import create_access_token"
text = text.replace("from scp.security.jwt_guard import create_access_token", import_sys)

with open("benchmark/run_world_exam.py", "w", encoding="utf-8") as f:
    f.write(text)
