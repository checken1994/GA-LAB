import ast
import subprocess
from pathlib import Path

class MutationVisitor(ast.NodeTransformer):
    def __init__(self, target_line=None):
        self.mutated = False
        self.target_line = target_line
        self.mutations_made = 0

    def visit_Compare(self, node):
        self.generic_visit(node)
        if self.mutated: return node
        if self.target_line and getattr(node, 'lineno', -1) != self.target_line: return node
        
        new_ops = []
        for op in node.ops:
            if isinstance(op, ast.Eq): new_ops.append(ast.NotEq())
            elif isinstance(op, ast.NotEq): new_ops.append(ast.Eq())
            elif isinstance(op, ast.Lt): new_ops.append(ast.LtE())
            elif isinstance(op, ast.LtE): new_ops.append(ast.Lt())
            elif isinstance(op, ast.Gt): new_ops.append(ast.GtE())
            elif isinstance(op, ast.GtE): new_ops.append(ast.Gt())
            elif isinstance(op, ast.Is): new_ops.append(ast.IsNot())
            elif isinstance(op, ast.IsNot): new_ops.append(ast.Is())
            else: new_ops.append(op)
            
        if any(type(o) != type(no) for o, no in zip(node.ops, new_ops)):
            node.ops = new_ops
            self.mutated = True
            self.mutations_made += 1
        return node
        
    def visit_Constant(self, node):
        if self.mutated: return node
        if self.target_line and getattr(node, 'lineno', -1) != self.target_line: return node
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            node.value += 1
            self.mutated = True
            self.mutations_made += 1
        return node

def generate_mutants(file_path: Path):
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    mutants = []
    
    for i in range(1, len(source.splitlines()) + 1):
        if len(mutants) >= 5: break
        
        tree_copy = ast.parse(source)
        visitor = MutationVisitor(target_line=i)
        visitor.visit(tree_copy)
        if visitor.mutated:
            mutated_code = ast.unparse(tree_copy)
            mutants.append((i, mutated_code))
            
    return mutants

def run_mutation_tests(file_path_rel: str, test_file_path: str = None) -> float:
    """Run mutation tests and return mutation score (0.0 to 1.0)"""
    file_path = Path(file_path_rel).resolve()
    if not file_path.exists() or not file_path_rel.endswith(".py"):
        return 1.0
        
    try:
        mutants = generate_mutants(file_path)
    except Exception as e:
        print(f"[MutationEngine] Failed to generate mutants: {e}")
        return 1.0
        
    if not mutants:
        return 1.0
        
    if test_file_path is None:
        parts = Path(file_path_rel).parts
        if parts[0] == "scp": parts = parts[1:]
        test_file_name = "test_" + "_".join(parts)
        test_file = Path("tests") / test_file_name
        if not test_file.exists(): return 0.0
    else:
        test_file = Path(test_file_path)
        
    original_code = file_path.read_text(encoding="utf-8")
    killed = 0
    
    print(f"[MutationEngine] Running {len(mutants)} mutations on {file_path_rel} against {test_file.name}...")
    for lineno, mutated_code in mutants:
        try:
            file_path.write_text(mutated_code, encoding="utf-8")
            res = subprocess.run(["pytest", str(test_file)], capture_output=True, timeout=10)
            if res.returncode != 0:
                killed += 1
        except subprocess.TimeoutExpired:
            killed += 1
        finally:
            file_path.write_text(original_code, encoding="utf-8")
            
    score = killed / len(mutants)
    print(f"[MutationEngine] Score: {score*100:.1f}% ({killed}/{len(mutants)} killed)")
    return score
