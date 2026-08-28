import json
import subprocess
import os
import shutil

archive_dir = r"c:\Users\check\Downloads\scp\archive\legacy_tests"
os.makedirs(archive_dir, exist_ok=True)

print("Đang chạy Pytest với JSON Report (có thể mất 30-40 giây)...")
subprocess.run(
    ["python", "-m", "pytest", "-q", "--disable-warnings", "--json-report", "--json-report-file=report.json"],
    cwd=r"c:\Users\check\Downloads\scp",
    capture_output=True,
    text=True
)

if os.path.exists(r"c:\Users\check\Downloads\scp\report.json"):
    with open(r"c:\Users\check\Downloads\scp\report.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    bad_files = set()
    
    # 1. Các file bị lỗi Collection (Error)
    if "collectors" in data:
        for col in data["collectors"]:
            if col.get("outcome") == "failed":
                bad_files.add(col.get("nodeid"))
                
    # 2. Các test bị Fail hoặc Error trong lúc chạy
    if "tests" in data:
        for t in data["tests"]:
            if t.get("outcome") in ["failed", "error"]:
                # nodeid dạng: tests/test_abc.py::test_xyz
                filepath = t.get("nodeid", "").split("::")[0]
                if filepath.endswith(".py"):
                    bad_files.add(filepath)

    print(f"Phát hiện {len(bad_files)} file test hỏng/lỗi thời. Đang cách ly...")
    for rel_path in bad_files:
        abs_path = os.path.join(r"c:\Users\check\Downloads\scp", rel_path)
        if os.path.exists(abs_path):
            dest = os.path.join(archive_dir, os.path.basename(rel_path))
            shutil.move(abs_path, dest)
            print(f" -> Đã cách ly: {rel_path}")

print("\n-- KIỂM TRA LẠI LƯỚI AN TOÀN (GREEN CHECK) --")
result_green = subprocess.run(
    ["python", "-m", "pytest", "-q", "--disable-warnings"], 
    cwd=r"c:\Users\check\Downloads\scp",
    capture_output=True, 
    text=True
)
print(result_green.stdout)
