from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.web_control.browser_session import BrowserSession


async def main() -> None:
    browser = BrowserSession()
    targets = await browser.targets()
    page = next((item for item in targets if item.get('type') == 'page' and any(host in str(item.get('url', '')).lower() for host in ('chatgpt.com', 'chat.openai.com'))), None)
    if not page:
        print(json.dumps({'success': False, 'error': 'No ChatGPT page'}, ensure_ascii=False))
        return
    expression = r'''(() => {
      const body = document.body?.innerText || '';
      const inputs = Array.from(document.querySelectorAll('textarea, [contenteditable="true"], input')).map((el) => ({
        tag: el.tagName,
        placeholder: el.getAttribute('placeholder') || '',
        aria: el.getAttribute('aria-label') || '',
        value: ('value' in el ? el.value : el.textContent || '').slice(0, 500),
        valueLen: ('value' in el ? el.value : el.textContent || '').length,
        hasExpectedValue: ('value' in el ? el.value : el.textContent || '').includes('SCP_CHATGPT_TEST_OK')
      }));
      const buttons = Array.from(document.querySelectorAll('button')).map((el) => ({
        text: (el.innerText || '').trim().slice(0, 100),
        aria: el.getAttribute('aria-label') || '',
        title: el.getAttribute('title') || '',
        testid: el.getAttribute('data-testid') || '',
        disabled: !!el.disabled
      })).filter((item) => /send|gửi|submit|prompt|message|tin nhắn/i.test([item.text, item.aria, item.title, item.testid].join(' ')));
      const textarea = document.querySelector('textarea');
      const form = textarea?.closest('form');
      const formButtons = Array.from(form?.querySelectorAll('button') || []).map((el, index) => ({
        index,
        text: (el.innerText || '').trim().slice(0, 100),
        aria: el.getAttribute('aria-label') || '',
        title: el.getAttribute('title') || '',
        testid: el.getAttribute('data-testid') || '',
        name: el.getAttribute('name') || '',
        className: el.className || '',
        disabled: !!el.disabled,
        html: el.outerHTML.slice(0, 500)
      }));
      return {
        url: location.href,
        title: document.title,
        hasExpected: body.includes('SCP_CHATGPT_TEST_OK'),
        tail: body.slice(-12000),
        inputs,
        buttons,
        formExists: !!form,
        formButtons
      };
    })()'''
    result = await browser.evaluate(expression, page)
    print('url=' + str(result.get('url', '')))
    print('title=' + str(result.get('title', '')))
    print('hasExpected=' + str(result.get('hasExpected', False)))
    print('tail=' + str(result.get('tail', ''))[-4000:])
    for index, item in enumerate(result.get('inputs', [])):
        print('input' + str(index) + '|tag=' + str(item.get('tag')) + '|valueLen=' + str(item.get('valueLen')) + '|hasExpectedValue=' + str(item.get('hasExpectedValue')) + '|placeholder=' + repr(item.get('placeholder', '')))
    print('formExists=' + str(result.get('formExists', False)))
    print('formButtonCount=' + str(len(result.get('formButtons', []))))
    for index, item in enumerate(result.get('formButtons', [])):
        print('formButton' + str(index) + '|aria=' + repr(item.get('aria', '')) + '|title=' + repr(item.get('title', '')) + '|testid=' + repr(item.get('testid', '')) + '|name=' + repr(item.get('name', '')) + '|disabled=' + str(item.get('disabled', False)) + '|html=' + repr(item.get('html', '')[:300]))


if __name__ == '__main__':
    asyncio.run(main())
