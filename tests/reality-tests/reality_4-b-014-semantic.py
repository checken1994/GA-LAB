"""Reality test: BareExceptPass is not semantic-equivalent to except Exception: pass."""
from __future__ import annotations

import ast
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _handler_at(path: Path, line: int) -> ast.ExceptHandler:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.lineno == line
    ]
    assert len(matches) == 1, f"expected one except handler at {path}:{line}, got {len(matches)}"
    return matches[0]


def _run_bare(exc_type: type[BaseException]) -> str:
    try:
        raise exc_type()
    except:  # noqa: E722 - intentional baseline semantics
        return "caught"


def _run_typed(exc_type: type[BaseException]) -> str:
    try:
        try:
            raise exc_type()
        except Exception:  # noqa: BLE001 - semantic comparison target
            return "caught"
    except BaseException:  # noqa: BLE001 - observe propagation
        return "propagated"


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    checks = {
        root / "scp/autofix/speculative_prefixer.py": 559,
        root / "scp/autofix/type_flow_verifier.py": 717,
    }
    for path, line in checks.items():
        handler = _handler_at(path, line)
        assert handler.type is not None, f"{path}:{line} is a bare except unexpectedly"
        assert handler.body, f"{path}:{line} has an empty typed exception handler"
        assert not (len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)), f"{path}:{line} still uses typed-except-pass"
        print(f"PASS classification: {path.name}:{line} is typed-exception with explicit handling, not bare-except-pass")

    source = "def f():\n    try:\n        return 1\n    except:\n        pass\n"
    from scp.autofix.speculative_prefixer import SpeculativeCache

    with tempfile.TemporaryDirectory(prefix="r44_4b014_") as tmp:
        cache = SpeculativeCache(cache_file=str(Path(tmp) / "cache.json"))
        stored = cache.prefetch_candidates("historical.py", ["bare_except_pass"], source_override=source)
        file_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
        candidate = cache.lookup(file_sha, "bare_except_pass")
        assert stored == 1 and candidate is not None
        assert "except Exception:" in candidate.patched_snippet
        ast.parse(candidate.full_patched_source)
        print("PASS candidate: generated patch parses and narrows handler")

    assert _run_bare(ValueError) == _run_typed(ValueError) == "caught"
    print("PASS semantic matrix: ordinary Exception behavior agrees")

    for exc_type in (KeyboardInterrupt, SystemExit, GeneratorExit):
        bare = _run_bare(exc_type)
        typed = _run_typed(exc_type)
        assert bare == "caught" and typed == "propagated"
        print(f"PASS counterexample: {exc_type.__name__} differs (bare={bare}, typed={typed})")

    print("RESULT: semantic equivalence is disproved outside Exception; promotion must remain gated")


if __name__ == "__main__":
    main()
