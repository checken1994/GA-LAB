# Auto-extracted from cross_func_taint_scanner.py
from __future__ import annotations
import ast
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from scp.autofix.classifier import BugReport, BugTier
from scp.autofix.scanners.taint_flow_scanner import _CWE_TITLES, _HEURISTIC_PARAM_NAMES, _MARSHAL_FUNCS, _PICKLE_FUNCS, _SQL_EXECUTE_NAMES, _SUBPROCESS_FUNCS, _XSS_BUILDERS, _collect_names, _is_sanitizer_call, _is_source, _iter_python_files

def scan_file(path: Path) -> list[BugReport]:
    """Scan a single Python file for CROSS-FUNCTION taint bugs.

    Builds a call graph from scp/ + the target file, then walks the target
    file's functions with cross-function awareness. Reports bugs whose
    CALLER is in the target file.

    NOTE: this scanner ONLY reports cross-function bugs (source and sink in
    DIFFERENT functions). Intra-function bugs are reported by
    taint_flow_scanner.py's scan_file().

    Args:
        path: Path to a .py file.

    Returns:
        List of BugReports with bug_type="CrossFuncTaint_CWE-XXX".
    """
    path = Path(path)
    base = _get_scp_call_graph()
    scanner = _clone_call_graph(base)
    scanner.add_file(path)
    scanner.run_fixpoint()
    return scanner.detect_bugs(only_in_files={str(path)})
