from .cross_func_taint_scanner_parts._classify_sink_xfunc import _classify_sink_xfunc
from .cross_func_taint_scanner_parts.functioninfo import FunctionInfo
from .cross_func_taint_scanner_parts._callgraphbuilder import _CallGraphBuilder
from .cross_func_taint_scanner_parts._run_fixpoint import _run_fixpoint
from .cross_func_taint_scanner_parts._functiondetector import _FunctionDetector
from .cross_func_taint_scanner_parts._crossfuncscanner import _CrossFuncScanner
from .cross_func_taint_scanner_parts._get_scp_call_graph import _get_scp_call_graph
from .cross_func_taint_scanner_parts.scan_file import scan_file
from .cross_func_taint_scanner_parts.scan_scp import scan_scp

from __future__ import annotations
import ast
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from scp.autofix.classifier import BugReport, BugTier
from scp.autofix.scanners.taint_flow_scanner import _CWE_TITLES, _HEURISTIC_PARAM_NAMES, _MARSHAL_FUNCS, _PICKLE_FUNCS, _SQL_EXECUTE_NAMES, _SUBPROCESS_FUNCS, _XSS_BUILDERS, _collect_names, _is_sanitizer_call, _is_source, _iter_python_files
logger = logging.getLogger('scp.autofix.scanners.cross_func_taint')
_SCP_ROOT = Path(__file__).resolve().parent.parent.parent
_MAX_FILES = 500
_MAX_FIXPOINT_ROUNDS = 10
__all__ = ['scan_file', 'scan_scp']
_BUILTIN_INPUT_FUNCS: frozenset[str] = frozenset({'input', 'raw_input'})

def _xfunc_is_source(node) -> tuple[str, str] | None:
    """Extended SOURCE detection: V10's _is_source + builtin input()/raw_input()."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in _BUILTIN_INPUT_FUNCS:
            return ('cli', f'{node.func.id}()')
    return _is_source(node)

@dataclass
class CallEdge:
    """An edge in the call graph: caller F calls callee G with F's param as arg.

    Only recorded for calls where (a) the callee is a bare-name call (so we
    can resolve it by simple name) and (b) one of the args is a param of F.
    """
    callee_name: str
    arg_param: str
    call_line: int
    arg_pos: int
    in_return: bool

@dataclass
class SinkHit:
    """A sink reached by a param (directly in F, or transitively via a callee)."""
    cwe: str
    sink_name: str
    sink_line: int
    via_callee: str | None = None
    via_callee_file: str | None = None
    via_callee_param: str | None = None
_SCP_CALL_GRAPH_CACHE: _CrossFuncScanner | None = None

def _clone_call_graph(base: _CrossFuncScanner) -> _CrossFuncScanner:
    """Clone a call graph (for scan_file to extend with a target file)."""
    new = _CrossFuncScanner()
    for qualname, info in base.funcs_by_qualname.items():
        new.funcs_by_qualname[qualname] = info
    for name, lst in base.funcs_by_name.items():
        new.funcs_by_name[name] = list(lst)
    new._fixpoint_done = True
    return new
