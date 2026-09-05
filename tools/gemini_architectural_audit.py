import os
import ast
from collections import defaultdict

root_dir = r"c:\Users\check\Downloads\scp"
py_files = []
total_lines = 0

for dirpath, _, filenames in os.walk(root_dir):
    if '.git' in dirpath or '.venv' in dirpath or '.agents' in dirpath:
        continue
    for f in filenames:
        if f.endswith('.py'):
            filepath = os.path.join(dirpath, f)
            py_files.append(filepath)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as file:
                total_lines += len(file.readlines())

print(f"Found {len(py_files)} Python files with {total_lines} lines.")

stubs = []
dummy_returns = []

for filepath in py_files:
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check for empty/pass functions
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    stubs.append(f"{filepath}:{node.lineno} - {node.name}")
                # Check for dummy returns
                if len(node.body) == 1 and isinstance(node.body[0], ast.Return):
                    ret_val = node.body[0].value
                    if isinstance(ret_val, ast.Dict) and len(ret_val.keys) == 1:
                        if getattr(ret_val.keys[0], 'value', None) == 'ok' or getattr(ret_val.keys[0], 's', None) == 'ok':
                            dummy_returns.append(f"{filepath}:{node.lineno} - {node.name} returns {ast.unparse(ret_val)}")
    except Exception:
        pass

print(f"\nFound {len(stubs)} stubbed functions (pass).")
print(f"Found {len(dummy_returns)} dummy returns (ok: True).")

if len(dummy_returns) > 0:
    print("\nSample Dummy Returns:")
    for d in dummy_returns[:10]:
        print("  -", d)

