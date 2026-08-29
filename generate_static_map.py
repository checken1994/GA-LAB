import os
import ast
from pathlib import Path

def get_ast_info(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
        
        classes = []
        functions = []
        
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = []
                for n in node.body:
                    if isinstance(n, ast.FunctionDef) or isinstance(n, ast.AsyncFunctionDef):
                        methods.append(n.name)
                classes.append({'name': node.name, 'methods': methods})
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                functions.append(node.name)
                
        return {'classes': classes, 'functions': functions}
    except Exception as e:
        return {'error': str(e)}

def build_markdown(root_dir, include_dirs):
    lines = ["# SCP Static Architecture Map", ""]
    lines.append("> **Lưu ý:** Đây là Bản đồ Tĩnh (Static Map) trích xuất bằng AST. Nó liệt kê 100% các class và hàm hiện có trong mã nguồn, nhưng KHÔNG mô tả các chuỗi thực thi Runtime.")
    lines.append("")
    
    for search_dir in include_dirs:
        base_path = Path(root_dir) / search_dir
        if not base_path.exists():
            continue
            
        lines.append(f"## Thư mục: {search_dir}/")
        for root, _, files in os.walk(base_path):
            py_files = [f for f in files if f.endswith('.py')]
            if not py_files:
                continue
                
            rel_root = os.path.relpath(root, root_dir)
            lines.append(f"\n### 📁 {rel_root.replace(os.sep, '/')}")
            
            for file in sorted(py_files):
                full_path = os.path.join(root, file)
                info = get_ast_info(full_path)
                
                lines.append(f"- **📄 {file}**")
                
                if 'error' in info:
                    lines.append(f"  - *(Lỗi parse AST: {info['error']})*")
                    continue
                    
                for cls in info['classes']:
                    lines.append(f"  - 🟦 class {cls['name']}")
                    for method in cls['methods']:
                        lines.append(f"    - 🔸 def {method}")
                        
                for func in info['functions']:
                    lines.append(f"  - 🟢 def {func}")
                    
        lines.append("")
        
    return "\n".join(lines)

if __name__ == '__main__':
    project_root = Path('.').resolve()
    # Only scan these specific directories to avoid .venv
    dirs_to_scan = ['scp']
    
    md_content = build_markdown(project_root, dirs_to_scan)
    
    # Save to the artifacts directory so the agent can load it
    out_path = Path(os.environ.get('APPDATA_DIR', '.')) / 'scp_static_map.md'
    with open('scp_static_map.md', 'w', encoding='utf-8') as f:
        f.write(md_content)
        
    print("Static map generated successfully.")
