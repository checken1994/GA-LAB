from .llm_fix_parts._top_systems_references import _top_systems_references
from .llm_fix_parts._generate_bare_except_fix import _generate_bare_except_fix
from .llm_fix_parts._call_smart_llm import _call_smart_llm
from .llm_fix_parts._call_openrouter import _call_openrouter
from .llm_fix_parts._extract_search_replace_block import _extract_search_replace_block
from .llm_fix_parts.generate_fix_for_bug import generate_fix_for_bug
from .llm_fix_parts.process_bug_with_llm import process_bug_with_llm
from .llm_fix_parts._generate_deterministic_fix import _generate_deterministic_fix

"""
SCP LLM-Powered Fix Generator — lets SCP fix itself using LLM.

When AST scanner finds a bug with only text description (no code patch),
this module calls OpenRouter LLM to generate a proper search-replace fix
block that AutoFix can apply.

Flow:
  1. BugReport (text description, no code patch)
  2. Read buggy file + 5 lines context around bug line
  3. Send to LLM: "Fix this bug. Output <<<<<<< OLD / ======= / >>>>>>> NEW block."
  4. Parse LLM response, extract search-replace block
  5. AutoFix._apply_fix() applies the patch
  6. Verify: ast.parse + (optional) run pytest on affected file

This is the missing piece that makes "SCP tự fix SCP" actually work.
Before this, AutoFix reported "fixed" but patched=False (Bug #23).
"""
from __future__ import annotations
import json
import logging
import os
from scp.security.provider_keys import ProviderCredentialError, load_openrouter_keys
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
logger = logging.getLogger('scp.autofix.llm_fix')
_MAX_LLM_FIXES_PER_HOUR = 100
_recent_llm_calls: list[float] = []

def _check_rate_limit() -> bool:
    """Return True if we can make another LLM call."""
    global _recent_llm_calls
    now = time.time()
    _recent_llm_calls = [t for t in _recent_llm_calls if now - t < 3600]
    if len(_recent_llm_calls) >= _MAX_LLM_FIXES_PER_HOUR:
        return False
    _recent_llm_calls.append(now)
    return True
import re as _re_module
FIX_SYSTEM_PROMPT = 'You are a Python code fixer. Your task is to fix bugs using SEARCH/REPLACE blocks.\n\n## FORMAT (MUST FOLLOW EXACTLY)\n\n<<<<<<< SEARCH\n[exact code to find - including indentation]\n=======\n[fixed code - including indentation]\n>>>>>>> REPLACE\n\n## RULES\n1. Output ONLY the SEARCH/REPLACE block — no explanations before/after.\n2. SEARCH must match the EXACT code in the file (including spaces/indentation).\n3. REPLACE must be valid Python (preserves indentation).\n4. Do NOT add imports unless absolutely necessary.\n5. If you cannot fix the bug, output exactly: NO_FIX_POSSIBLE\n\n## EXAMPLE\n\nBug: BareExceptPass at line 5\nFile code:\n    try:\n        do_something()\n    except Exception as e:\n        pass\n\nCorrect output:\n<<<<<<< SEARCH\n    except Exception as e:\n        pass\n=======\n    except Exception as e:\n        logger.warning(repr(e))\n>>>>>>> REPLACE\n\n## YOUR TASK\n\nBug type: {bug_type}\nDescription: {bug_description}\nFile: {file_path}\nLine: {line_number}\n\nCode context (line numbers shown as `# line N >>>` comments — the `>>>` marker shows the buggy line; do NOT include these comments in your SEARCH block):\n{code_context}\n\nGenerate the SEARCH/REPLACE block to fix this bug:'

def _build_fix_prompt(bug, code_context: str) -> str:
    """Build improved prompt with few-shot example.

    [OPT-30] WHY: replaces the inline prose prompt that had 7/15 LLM failures.
    Now uses FIX_SYSTEM_PROMPT template with explicit rules + worked example.
    [2026-08-29] Appends TOP-1% knowledge-warehouse references when available.
    """
    prompt = FIX_SYSTEM_PROMPT.format(bug_type=bug.bug_type, bug_description=getattr(bug, 'description', 'N/A'), file_path=bug.file, line_number=bug.line, code_context=code_context)
    references = _top_systems_references(bug)
    if references:
        prompt += '\n\n[SCP TOP-1% KNOWLEDGE WAREHOUSE — tham chiếu thực hành tốt đã thu thập, chỉ dùng để tham khảo kiến trúc, không copy mù]\n' + references
    return prompt
_SIMPLE_BUG_TYPES = {'BareExceptPass', 'UnusedImport', 'UnusedVariable', 'PossiblyUndefinedName', 'MissingDocstring'}
_COMPLEX_BUG_TYPES = {'SQLInjection', 'SQLInjectionRisk', 'RaceCondition', 'LogicFlow', 'TypeContract', 'SecurityIssue', 'PathTraversal', 'NullSafety', 'XSSVulnerability'}
_MEDIUM_BUG_TYPES = {'ResourceLeak', 'DeadCode', 'RoutingGap', 'SchemaMismatch', 'PerformanceIssue', 'APIWiring'}

def select_provider_for_bug(bug_type: str) -> str:
    """[ROOT-FIX 44-A] DEPRECATED — always returns "ollama".

    [OPT-17] Originally picked per-bug-type cloud provider (deepseek for
    medium, anthropic for complex, openrouter for unknown). Removed in 44-A
    because user has no DeepSeek/Anthropic/OpenAI API keys. All AutoFix
    calls now go through Ollama via gateway.chat_sync(task="autofix").

    Returns "ollama" so legacy callers (e.g. engine.py attribute logging)
    don't break. Smart routing happens in the gateway via task= parameter.
    """
    return 'ollama'

def get_llm_for_bug(bug_type: str):
    """Get LLM gateway for the bug type.

    [ROOT-FIX 44-A] All bug types now use the same gateway — routing is
    handled via task="autofix" parameter on chat_sync(). The
    set_preferred_provider call is now a no-op (kept for backward compat).
    """
    try:
        from scp.llm_gateway import get_gateway
        gateway = get_gateway()
        preferred = select_provider_for_bug(bug_type)
        if hasattr(gateway, 'set_preferred_provider'):
            gateway.set_preferred_provider(preferred)
        return gateway
    except Exception as e:
        logger.debug(f'[llm_fix] get_llm_for_bug({bug_type}) gateway unavailable: {e}')
        return None

def _validate_openrouter_base_url(base_url: str) -> str:
    """Return a safe OpenRouter base URL for the direct fallback client."""
    parsed = urllib.parse.urlparse(str(base_url).rstrip('/'))
    allowed_hosts = {'openrouter.ai', 'api.openrouter.ai', 'localhost', '127.0.0.1'}
    if parsed.hostname not in allowed_hosts:
        raise ValueError(f'Unsupported OpenRouter host: {parsed.hostname!r}')
    if parsed.hostname in {'openrouter.ai', 'api.openrouter.ai'} and parsed.port not in {None, 443}:
        raise ValueError('OpenRouter HTTPS endpoint must use the default port')
    if parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1'}:
        raise ValueError(f'Unsupported OpenRouter scheme: {parsed.scheme!r}')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('OpenRouter base URL must not contain credentials or query data')
    if not parsed.netloc or not parsed.path:
        raise ValueError('OpenRouter base URL must include an API path')
    return parsed.geturl()
