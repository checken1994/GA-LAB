from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.web_control.multi_source_orchestrator import MultiSourceOrchestrator


class FakeAI:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def ask_ai(self, provider: str, question: str, **kwargs):
        self.calls.append(provider)
        if provider == 'chatgpt':
            return {'success': False, 'error': 'No AI prompt input found on current page', 'method': 'mock-ui-failure'}
        if provider == 'claude':
            return {'success': True, 'answer': 'CLAUDE_FALLBACK_OK', 'method': 'mock-browser'}
        if provider == 'gemini':
            return {'success': True, 'answer': 'GEMINI_FALLBACK_OK', 'method': 'mock-browser'}
        return {'success': False, 'error': 'unexpected provider'}


class FakeNavigator:
    async def search_public(self, query: str, max_results: int = 8):
        return {'success': True, 'results': [{'title': 'web fallback', 'url': 'https://example.com', 'provider': 'mock-web'}], 'untrustedData': True}


async def main() -> None:
    fake_ai = FakeAI()
    result = await MultiSourceOrchestrator(fake_ai, FakeNavigator()).run(
        'SCP provider failover test',
        providers=['chatgpt', 'claude', 'gemini'],
        approved=True,
        use_browser=True,
        allow_local=False,
    )
    ai_by_provider = {item['provider']: item['result'] for item in result['aiResults']}
    checks = {
        'chatgpt_failed_ui': ai_by_provider.get('chatgpt', {}).get('success') is False,
        'claude_was_tried': 'claude' in fake_ai.calls,
        'claude_succeeded': ai_by_provider.get('claude', {}).get('success') is True,
        'gemini_was_tried': 'gemini' in fake_ai.calls,
        'web_fallback_succeeded': result.get('webSearch', {}).get('success') is True,
        'overall_success': result.get('success') is True,
    }
    print('calls=' + ','.join(fake_ai.calls))
    print('successfulAI=' + ','.join(result.get('successfulAIProviders', [])))
    print('checks=' + json.dumps(checks, ensure_ascii=False))
    print('PASS=' + str(all(checks.values())))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
