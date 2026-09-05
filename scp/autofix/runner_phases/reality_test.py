import ast
import inspect
import importlib.util
from pathlib import Path

def run_reality_test(bug_id: str = None, file_path: str = None, exercise_callables: bool = True, **kwargs):
    if not file_path or not Path(file_path).exists():
        return {"ok": False, "status": "UNVERIFIED", "reason": "file not found"}

    try:
        source = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"ok": False, "status": "UNVERIFIED", "reason": f"Syntax error: {e}"}

    callables_exercised = 0
    if exercise_callables:
        try:
            module_name = Path(file_path).stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            # Do NOT cache in sys.modules to prevent test pollution
            spec.loader.exec_module(module)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    func = getattr(module, node.name, None)
                    if callable(func):
                        sig = inspect.signature(func)
                        mock_args = []
                        for param in sig.parameters.values():
                            if param.annotation == str: mock_args.append("test")
                            elif param.annotation == int: mock_args.append(1)
                            elif param.default != inspect.Parameter.empty: mock_args.append(param.default)
                            else: mock_args.append("test")
                        
                        try:
                            func(*mock_args)
                        except Exception as e:
                            # Actually fail if execution throws an exception
                            return {"ok": False, "status": "UNVERIFIED", "reason": f"Execution error in {node.name}: {e}"}
                        callables_exercised += 1
        except Exception as e:
            return {"ok": False, "status": "UNVERIFIED", "reason": f"Module load/execution error: {e}"}

    return {
        "ok": True,
        "status": "VERIFIED",
        "reason": f"reality test passed, exercised {callables_exercised} callables",
        "callables_exercised": callables_exercised
    }
