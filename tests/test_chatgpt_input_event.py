from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.web_control.browser_session import BrowserSession

PROMPT = 'Trả lời đúng chuỗi sau và không thêm chữ nào: SCP_CHATGPT_TEST_OK'


async def main() -> None:
    browser = BrowserSession()
    targets = await browser.targets()
    page = next((item for item in targets if item.get('type') == 'page' and 'chatgpt.com' in str(item.get('url', '')).lower()), None)
    if not page:
        print(json.dumps({'success': False, 'error': 'No ChatGPT page'}, ensure_ascii=False))
        return
    expression = f'''(async () => {{
      const prompt = {json.dumps(PROMPT, ensure_ascii=False)};
      const input = document.querySelector('textarea, [contenteditable="true"]');
      if (!input) return {{success: false, error: 'no input'}};
      input.focus();
      if (typeof input.select === 'function') input.select();
      const execResult = document.execCommand('insertText', false, prompt);
      await new Promise((resolve) => setTimeout(resolve, 700));
      const form = input.closest('form');
      return {{success: true, execResult, value: ('value' in input ? input.value : input.textContent || ''), formButtons: Array.from(form?.querySelectorAll('button') || []).map((b) => ({{disabled: !!b.disabled, aria: b.getAttribute('aria-label') || '', testid: b.getAttribute('data-testid') || ''}}))}};
    }})()'''
    result = await browser.evaluate(expression, page)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == '__main__':
    asyncio.run(main())
