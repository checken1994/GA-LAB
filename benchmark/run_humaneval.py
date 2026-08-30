import asyncio
import json
import time
import urllib.request
import urllib.error
import sys
import os
import subprocess
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scp.security.jwt_guard import create_access_token

BASE_URL = os.environ.get("SCP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

def extract_python_code(text: str) -> str:
    if "```python" in text:
        return text.split("```python")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()

async def run_humaneval(file_path: str):
    print(f"--- STARTING HUMANEVAL BENCHMARK: {file_path} ---")
    
    try:
        req = urllib.request.Request(f"{BASE_URL}/health", method="GET")
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print("ERROR: SCP Server is not running. Please run `python -m scp` first.")
        return

    if file_path.endswith(".gz"):
        import gzip
        open_fn = gzip.open
    else:
        open_fn = open

    tasks = []
    with open_fn(file_path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            tasks.append(json.loads(line))
            
    print(f"-> Loaded {len(tasks)} tasks. Generating completions via API server...")
    
    samples_file = "humaneval_samples.jsonl"
    
    with open(samples_file, "w", encoding="utf-8") as out_f:
        for i, task in enumerate(tasks):
            task_id = task["task_id"]
            prompt = task["prompt"]
            
            question = f"Please complete the following Python code:\n```python\n{prompt}\n```\nProvide ONLY the Python code without any explanation."
            
            body = json.dumps({
                "question": question,
                "session_id": f"humaneval-{time.time()}",
                "contexts": [],
                "source": "scp_humaneval_benchmark"
            }).encode('utf-8')
            
            token = create_access_token({"sub": "benchmark-runner"})
            req = urllib.request.Request(f"{BASE_URL}/ask", data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}, method="POST")
            
            try:
                with urllib.request.urlopen(req) as response:
                    res_body = response.read().decode('utf-8')
                    res_json = json.loads(res_body)
                    raw_answer = res_json.get("answer", "")
                    
                    code_completion = extract_python_code(raw_answer)
                    
                    if code_completion.startswith(prompt.strip()):
                        code_completion = code_completion[len(prompt.strip()):]
                        
                    out_f.write(json.dumps({
                        "task_id": task_id,
                        "completion": code_completion
                    }) + "\n")
                    print(f"[{i+1}/{len(tasks)}] {task_id} generated.")
            except urllib.error.HTTPError as e:
                print(f"[{i+1}/{len(tasks)}] HTTP Error for {task_id}: {e.code}")
            except Exception as e:
                print(f"[{i+1}/{len(tasks)}] Error for {task_id}: {e}")
                
            out_f.flush()

    print(f"--- GENERATION COMPLETE. SAMPLES SAVED TO {samples_file} ---")
    
    print("--- RUNNING EVALPLUS EVALUATION ---")
    try:
        cmd = [
            sys.executable, "-m", "evalplus.evaluate", 
            "--dataset", "humaneval", 
            "--samples", samples_file
        ]
        print(f"Executing: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        print("--- EVALPLUS EVALUATION COMPLETE ---")
    except subprocess.CalledProcessError as e:
        print(f"EvalPlus evaluation failed: {e}")
    except FileNotFoundError:
        print("EvalPlus not found. Please install it using `pip install evalplus`.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_humaneval.py <path_to_humaneval.jsonl>")
        sys.exit(1)
        
    file_target = sys.argv[1]
    asyncio.run(run_humaneval(file_target))
