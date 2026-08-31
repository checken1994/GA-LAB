import os
import sys
import json
import time
import subprocess
from pathlib import Path
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.llm_gateway.client import chat_sync

def get_missing_lines(target_file_rel: str) -> list[int]:
    """Run coverage for a specific file and return missing line numbers."""
    # Convert scp/path/to/file.py -> scp.path.to.file
    mod_name = target_file_rel.replace("/", ".").replace("\\", ".")
    if mod_name.endswith(".py"):
        mod_name = mod_name[:-3]
    
    subprocess.run(
        ["pytest", f"--cov={mod_name}", "--cov-report=json", "tests/"],
        cwd=str(ROOT), capture_output=True
    )
    
    cov_file = ROOT / "coverage.json"
    if not cov_file.exists():
        return []
        
    try:
        data = json.loads(cov_file.read_text())
        files = data.get("files", {})
        # Find matching file in coverage data
        for fpath, fdata in files.items():
            if target_file_rel.replace("\\", "/") in fpath.replace("\\", "/"):
                return fdata.get("missing_lines", [])
    except Exception:
        pass
    return []

def run_test_file(test_file: Path) -> tuple[bool, str]:
    """Run pytest on a specific file and return (success, output)."""
    res = subprocess.run(["pytest", str(test_file)], cwd=str(ROOT), capture_output=True, text=True)
    return res.returncode == 0, res.stdout + "\n" + res.stderr

def autofix_test_generation(target_file_rel: str):
    """The SCP Autofix loop for generating and fixing tests."""
    missing = get_missing_lines(target_file_rel)
    if not missing:
        print(f"[TestFactory] {target_file_rel} already has 100% coverage. Skipping.")
        return

    target_path = ROOT / target_file_rel
    if not target_path.exists():
        return

    code_content = target_path.read_text(encoding="utf-8")
    
    # Map target file to test file: scp/runtime/slms.py -> tests/test_runtime_slms.py
    # or if there's an existing test file, use it.
    parts = Path(target_file_rel).parts
    if parts[0] == "scp":
        parts = parts[1:]
    test_file_name = "test_" + "_".join(parts)
    test_path = ROOT / "tests" / test_file_name
    
    existing_test = ""
    if test_path.exists():
        existing_test = test_path.read_text(encoding="utf-8")

    print(f"[TestFactory] Generating coverage for {target_file_rel} (missing {len(missing)} lines)")
    
    system_prompt = (
        "You are the SCP Test Factory Autofix Engine. Your goal is to write or update pytest code "
        "to achieve 100% coverage. Output ONLY valid Python code block with no markdown outside it. "
        "Do not write explanations."
    )
    
    context = (
        f"Target File: {target_file_rel}\n\nCode:\n```python\n{code_content}\n```\n\n"
        f"Missing Coverage Lines: {missing}\n\n"
    )
    if existing_test:
        context += f"Existing Test File ({test_file_name}):\n```python\n{existing_test}\n```\n\nModify or append to this test file to cover the missing lines."
    else:
        context += f"Create a new test file {test_file_name} to cover the missing lines."

    question = "Write the complete updated test file python code. Use standard pytest and unittest.mock if needed."
    
    for attempt in range(3):
        print(f"[TestFactory] Autofix attempt {attempt + 1}/3...")
        response, _ = chat_sync(question, context=context, system_prompt=system_prompt, task="test_factory")
        
        if not response:
            print("[TestFactory] LLM failed to respond.")
            return
            
        # Extract python code
        code_block = response
        if "```python" in response:
            code_block = response.split("```python")[1].split("```")[0].strip()
        elif "```" in response:
            code_block = response.split("```")[1].split("```")[0].strip()
            
        test_path.write_text(code_block, encoding="utf-8")
        
        success, output = run_test_file(test_path)
        if success:
            print(f"[TestFactory] SUCCESS! Tests for {target_file_rel} passed.")
            # Verify new coverage
            new_missing = get_missing_lines(target_file_rel)
            if not new_missing:
                print(f"[TestFactory] 100% Coverage achieved for {target_file_rel}!")
            else:
                print(f"[TestFactory] Coverage improved, but still missing: {new_missing}")
            break
        else:
            print(f"[TestFactory] Test failed. Feeding error back to Autofix...")
            context = f"The test failed with this output:\n```\n{output}\n```\n\nPlease fix the test code."
            question = "Rewrite the test file to fix this error. Output ONLY python code."

def watch_loop():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "watchdog"])
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

    class CodeWatcher(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory or not event.src_path.endswith(".py"):
                return
            rel_path = Path(event.src_path).relative_to(ROOT).as_posix()
            if not rel_path.startswith("scp/") or rel_path.startswith("scp/tests/"):
                return
            
            # Debounce or run in thread to not block watcher
            print(f"\n[Watcher] Detected core tech optimization in {rel_path}. Triggering Test Factory...")
            threading.Thread(target=autofix_test_generation, args=(rel_path,)).start()

    observer = Observer()
    observer.schedule(CodeWatcher(), path=str(ROOT / "scp"), recursive=True)
    observer.start()
    print("[TestFactory] Watchdog daemon activated. Listening for core tech updates...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch_loop()
    elif len(sys.argv) > 1 and sys.argv[1].endswith(".py"):
        autofix_test_generation(sys.argv[1])
    else:
        print("Usage: python scp_test_factory.py [--watch | path/to/target.py]")
