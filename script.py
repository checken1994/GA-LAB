import os
import ast
from pathlib import Path

root_dir = Path(r'c:\Users\check\Downloads\scp')
all_files = 0
py_files = []
md_files = []
for dirpath, dirnames, filenames in os.walk(root_dir):
    if '.git' in dirpath: continue
    for f in filenames:
        all_files += 1
        p = Path(dirpath) / f
        if f.endswith('.py'): py_files.append(p)
        elif f.endswith('.md'): md_files.append(p)

print(f"Total files (excluding .git): {all_files}")
print(f"Python files: {len(py_files)}")
print(f"Markdown files: {len(md_files)}")

class SkipVisitor(ast.NodeVisitor):
    def __init__(self):
        self.skips = []
        self.xfails = []
        
    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            # check for pytest.skip()
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'pytest' and node.func.attr == 'skip':
                self.skips.append(node.lineno)
            # check for pytest.mark.skip() / skipif()
            elif isinstance(node.func.value, ast.Attribute) and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == 'pytest' and node.func.value.attr == 'mark':
                if node.func.attr in ['skip', 'skipif']:
                    self.skips.append(node.lineno)
                elif node.func.attr == 'xfail':
                    self.xfails.append(node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name) and node.value.value.id == 'pytest' and node.value.attr == 'mark':
            if node.attr == 'skip':
                self.skips.append(node.lineno)
            elif node.attr == 'xfail':
                self.xfails.append(node.lineno)
        self.generic_visit(node)

skip_reports = []
for p in py_files:
    try:
        content = p.read_text(encoding='utf-8')
        tree = ast.parse(content, filename=str(p))
        visitor = SkipVisitor()
        visitor.visit(tree)
        if visitor.skips or visitor.xfails:
            skip_reports.append((str(p.relative_to(root_dir)), visitor.skips, visitor.xfails))
    except SyntaxError:
        pass

print("\nFA-02 Violations (AST analysis of pytest skip/xfail):")
for f, skips, xfails in skip_reports:
    print(f"  {f}: skips={skips}, xfails={xfails}")
