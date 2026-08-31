# Auto-extracted from cross_func_taint_scanner.py
from __future__ import annotations
import ast
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from scp.autofix.classifier import BugReport, BugTier
from scp.autofix.scanners.taint_flow_scanner import _CWE_TITLES, _HEURISTIC_PARAM_NAMES, _MARSHAL_FUNCS, _PICKLE_FUNCS, _SQL_EXECUTE_NAMES, _SUBPROCESS_FUNCS, _XSS_BUILDERS, _collect_names, _is_sanitizer_call, _is_source, _iter_python_files

def _get_scp_call_graph() -> _CrossFuncScanner:
    """Build (once) and return the scp/ call graph.

    Subsequent calls return the cached call graph. Used by scan_file() to
    avoid rebuilding the scp/ call graph for every file scan.
    """
    global _SCP_CALL_GRAPH_CACHE
    if _SCP_CALL_GRAPH_CACHE is not None:
        return _SCP_CALL_GRAPH_CACHE
    scanner = _CrossFuncScanner()
    files_added = 0
    for path in _iter_python_files(_SCP_ROOT, limit=_MAX_FILES):
        scanner.add_file(path)
        files_added += 1
    scanner.run_fixpoint()
    logger.info(f'[CrossFuncTaint] built scp/ call graph: {len(scanner.funcs_by_qualname)} functions across {files_added} files')
    _SCP_CALL_GRAPH_CACHE = scanner
    return scanner
