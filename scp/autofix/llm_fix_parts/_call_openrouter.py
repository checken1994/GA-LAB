# Auto-extracted from llm_fix.py
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
import re as _re_module

def _call_openrouter(prompt: str, max_tokens: int=4000) -> str | None:
    """Call OpenRouter LLM with the given prompt. Returns LLM response text.

    [FIX #25] TẠI SAO: was max_tokens=1500 — too small for multi-line code patches.
    LLM truncated output mid-block → search-replace regex didn't match → patched=False.
    Reality > Model: tested Bug #2 (PredictiveEngine) → LLM generated correct fix
    but truncated at "logger.info("V" — incomplete. After fix: max_tokens=4000.
    """
    try:
        _provider_keys = load_openrouter_keys()
    except ProviderCredentialError as exc:
        logger.warning('[llm_fix] Provider credential configuration rejected: %s', str(exc))
        _provider_keys = []
    api_key = _provider_keys[0] if _provider_keys else ''
    if not api_key:
        logger.warning('[llm_fix] No OpenRouter provider key configured; cannot generate fix')
        return None
    base_url = os.environ.get('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    model = os.environ.get('OPENROUTER_MODEL', 'meta-llama/llama-3.3-70b-instruct')
    payload = {'model': model, 'messages': [{'role': 'system', 'content': 'You are a Python code fixer. Output ONLY a search-replace block in this exact format (no markdown fences, no explanation):\n\n<<<<<<< SEARCH\n<exact current code>\n=======\n<fixed code>\n>>>>>>> REPLACE\n\nRules: (1) SEARCH must match the file exactly including indentation; (2) REPLACE must be valid Python; (3) if you cannot fix, output NO_FIX_POSSIBLE.'}, {'role': 'user', 'content': prompt}], 'max_tokens': max_tokens, 'temperature': 0.1}
    try:
        validated_base_url = _validate_openrouter_base_url(base_url)
        full_url = f'{validated_base_url}/chat/completions'
        req = urllib.request.Request(full_url, data=json.dumps(payload).encode('utf-8'), headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'HTTP-Referer': 'https://scp-vietnam.local', 'X-Title': 'SCP AutoFix'}, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('choices', [{}])[0].get('message', {}).get('content', '')
    except urllib.error.HTTPError as e:
        logger.warning(f"[llm_fix] OpenRouter HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
        return None
    except Exception as e:
        logger.warning(f'[llm_fix] OpenRouter call failed: {e}')
        return None
