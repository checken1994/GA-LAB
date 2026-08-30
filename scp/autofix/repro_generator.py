import json
import subprocess
import os

def generate_repro_test(issue_desc: str):
    # Tự viết một file Test tái lập lỗi (Failing Reproduction Test)
    # Trong môi trường thi đấu, SCP sẽ sinh test động từ Issue
    test_code = f\"\"\"
import pytest
def test_reproduction():
    # Issue: {issue_desc[:100]}
    assert False, "Failing test generated from issue for autofix loop"
\"\"\"
    with open("tests/test_dynamic_repro.py", "w", encoding="utf-8") as f:
        f.write(test_code)
    return "tests/test_dynamic_repro.py"
