import os
import re

TARGET_DIR = r"c:\Users\check\Downloads\scp"
# Các mẫu (pattern) chắp vá code cũ kỹ cần xóa bỏ
PATTERNS = r'\[(P\d+-\d+\s*FIX|FALSE-POS-FIX-\d+|V\d+(?:\.\d+-UPGRADE)?|R\d+-FIX-\d+|WIRING-FIX|G\d+-STUB|R\d+-\d+)\]'

print("1. ĐANG QUÉT VÀ XÓA CÁC TAG CHẮP VÁ (LEGACY TAGS)...")
clean_count = 0
for root, dirs, files in os.walk(TARGET_DIR):
    # Bỏ qua thư mục git và node_modules
    if ".git" in root or "node_modules" in root: continue
    
    for file in files:
        if file.endswith(('.py', '.md', '.env', '.jsonl')):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                cleaned_content = re.sub(PATTERNS, '', content, flags=re.IGNORECASE)
                
                if content != cleaned_content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(cleaned_content)
                    clean_count += 1
            except Exception:
                pass
print(f"-> Đã dọn dẹp bề mặt code cho {clean_count} file.")

print("\n2. XÓA BỎ ORCHESTRATOR (DEAD CODE)...")
orchestrator_path = os.path.join(TARGET_DIR, "scp", "runtime", "orchestrator.py")
if os.path.exists(orchestrator_path):
    os.remove(orchestrator_path)
    print("-> Đã tiêu diệt scp/runtime/orchestrator.py")

print("\n3. GỠ IMPORT CỦA ORCHESTRATOR TRONG JUDGE.PY...")
judge_path = os.path.join(TARGET_DIR, "scp", "runtime", "judge.py")
if os.path.exists(judge_path):
    with open(judge_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    with open(judge_path, 'w', encoding='utf-8') as f:
        for line in lines:
            if "PipelineOrchestrator" not in line and "orchestrator" not in line.lower():
                f.write(line)
    print("-> Đã gỡ bỏ mọi dấu vết của Orchestrator trong judge.py")

