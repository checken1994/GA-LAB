import os
import ast
import json
from pathlib import Path

def get_ast_info(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
        classes = []
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                classes.append({'name': node.name, 'methods': methods})
            elif isinstance(node, ast.FunctionDef):
                # Only top-level functions
                functions.append(node.name)
        return {'classes': classes, 'functions': functions}
    except Exception as e:
        return {'error': str(e)}

def map_project(root_dir):
    project_map = {}
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_dir)
                project_map[rel_path] = get_ast_info(full_path)
    return project_map

if __name__ == '__main__':
    scp_path = Path('scp').resolve()
    if not scp_path.exists():
        scp_path = Path('.').resolve()
    result = map_project(str(scp_path))
    
    with open('scp_full_ast_map.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f'Mapped {len(result)} Python files.')
