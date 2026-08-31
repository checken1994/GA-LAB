import argparse
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
        if self.mutated:
            return node
        if self.target_line and getattr(node, "lineno", -1) != self.target_line:
            return node

        new_ops = []
        for op in node.ops:
            if isinstance(op, ast.Eq):
                new_ops.append(ast.NotEq())
            elif isinstance(op, ast.NotEq):
                new_ops.append(ast.Eq())
            elif isinstance(op, ast.Lt):
                new_ops.append(ast.LtE())
            elif isinstance(op, ast.LtE):
                new_ops.append(ast.Lt())
            elif isinstance(op, ast.Gt):
                new_ops.append(ast.GtE())
            elif isinstance(op, ast.GtE):
                new_ops.append(ast.Gt())
            elif isinstance(op, ast.Is):
                new_ops.append(ast.IsNot())
            elif isinstance(op, ast.IsNot):
                new_ops.append(ast.Is())
            else:
                new_ops.append(op)

        if any(type(o) != type(no) for o, no in zip(node.ops, new_ops)):
            node.ops = new_ops
            self.mutated = True
            self.mutations_made += 1
        return node

    def visit_Constant(self, node):
        if self.mutated:
            return node
        if self.target_line and getattr(node, "lineno", -1) != self.target_line:
            return node
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            node.value += 1
            self.mutated = True
            self.mutations_made += 1
        return node


def generate_mutants(file_path: Path):
    source = file_path.read_text(encoding="utf-8")
    ast.parse(source)
    mutants = []

    for i in range(1, len(source.splitlines()) + 1):
        if len(mutants) >= 5:
            break

        tree_copy = ast.parse(source)
        visitor = MutationVisitor(target_line=i)
        visitor.visit(tree_copy)
        if visitor.mutated:
            mutants.append((i, ast.unparse(tree_copy)))

    return mutants


def _resolve_test_file(file_path_rel: str, test_file_path: str | None) -> Path:
    if test_file_path is not None:
        test_file = Path(test_file_path)
    else:
        parts = list(Path(file_path_rel).parts)
        if parts and parts[0] == "scp":
            parts = parts[1:]
        test_file = Path("tests") / ("test_" + "_".join(parts))
    if not test_file.exists():
        raise FileNotFoundError(f"mutation target has no test file: {test_file}")
    return test_file


def run_mutation_tests(file_path_rel: str, test_file_path: str | None = None) -> float:
    """Run mutation tests and return a real score in [0, 1].

    Infrastructure errors are not equivalent to a perfect score. Missing targets,
    parser failures, missing tests, pytest launch errors, and zero generated mutants
    raise instead of silently returning 1.0.
    """
    file_path = Path(file_path_rel).resolve()
    if not file_path_rel.endswith(".py"):
        raise ValueError(f"mutation target must be a Python file: {file_path_rel}")
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    mutants = generate_mutants(file_path)
    if not mutants:
        raise RuntimeError(f"no supported mutants generated for {file_path_rel}")

    test_file = _resolve_test_file(file_path_rel, test_file_path)
    original_code = file_path.read_text(encoding="utf-8")
    killed = 0

    print(
        f"[MutationEngine] Running {len(mutants)} mutations on "
        f"{file_path_rel} against {test_file.name}..."
    )
    for lineno, mutated_code in mutants:
        try:
            file_path.write_text(mutated_code, encoding="utf-8")
            res = subprocess.run(
                ["pytest", str(test_file)],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if res.returncode == 0:
                print(f"[MutationEngine] SURVIVED line {lineno}")
            elif res.returncode == 1:
                killed += 1
            else:
                raise RuntimeError(
                    f"pytest infrastructure/collection error for mutant at line {lineno}: "
                    f"returncode={res.returncode}; stderr={res.stderr[-1000:]!r}"
                )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"pytest timed out for mutant at line {lineno}") from exc
        finally:
            file_path.write_text(original_code, encoding="utf-8")

    score = killed / len(mutants)
    print(f"[MutationEngine] Score: {score*100:.1f}% ({killed}/{len(mutants)} killed)")
    return score


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed mutation gate")
    parser.add_argument("target")
    parser.add_argument("--test", required=True, dest="test_file")
    parser.add_argument("--min-score", type=float, default=0.0)
    args = parser.parse_args()

    if not 0.0 <= args.min_score <= 1.0:
        raise SystemExit("--min-score must be within [0, 1]")

    score = run_mutation_tests(args.target, args.test_file)
    if score < args.min_score:
        print(
            f"[MutationEngine] FAIL: score {score:.3f} below required {args.min_score:.3f}"
        )
        return 1
    print(f"[MutationEngine] PASS: score {score:.3f} >= {args.min_score:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
