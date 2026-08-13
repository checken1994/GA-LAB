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
    page = next((item for item in targets if item.get('type') == 'page' and '127.0.0.1:3000' in str(item.get('url', ''))), None)
    if not page:
        print(json.dumps({'success': False, 'error': 'No dashboard page'}, ensure_ascii=False))
        return
    await browser.cdp_command('Page.reload', {'ignoreCache': True}, page)
    await asyncio.sleep(3)
    before = await browser.evaluate('''(() => ({
      url: location.href,
      title: document.title,
      hasSearchLabel: (document.body?.innerText || '').includes('Tìm kiếm Internet độc lập'),
      hasPlaceholder: !!document.querySelector('input[placeholder*="SCP self correcting process"]'),
      buttons: Array.from(document.querySelectorAll('button')).map((b) => (b.innerText || '').trim()).filter(Boolean).slice(0, 40)
    }))()''', page)
    expression = '''(async () => {
      const input = document.querySelector('input[placeholder*="SCP self correcting process"]');
      if (!input) return {success: false, error: 'search input not found'};
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(input, 'SCP self correcting process');
      input.dispatchEvent(new Event('input', {bubbles: true}));
      input.dispatchEvent(new Event('change', {bubbles: true}));
      await new Promise((resolve) => setTimeout(resolve, 300));
      const button = Array.from(document.querySelectorAll('button')).find((b) => (b.innerText || '').includes('Tìm trên Internet'));
      if (!button) return {success: false, error: 'search button not found'};
      button.click();
      await new Promise((resolve) => setTimeout(resolve, 4000));
      const body = document.body?.innerText || '';
      return {
        success: true,
        hasDuckDuckGo: body.toLowerCase().includes('duckduckgo'),
        hasBing: body.toLowerCase().includes('bing'),
        hasUntrustedLabel: body.includes('Dữ liệu cần kiểm chứng'),
        resultLinkCount: Array.from(document.querySelectorAll('a[target="_blank"]')).length,
        bodyTail: body.slice(-5000)
      };
    })()'''
    apiProbe = await browser.evaluate('''(async () => {
      try {
        const response = await fetch('/api/scp/v3/web/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({query: 'SCP self correcting process', maxResults: 3})});
        const data = await response.json().catch(() => ({}));
        return {status: response.status, success: !!data.success, count: Array.isArray(data.results) ? data.results.length : 0, error: data.error || ''};
      } catch (error) {
        return {status: 0, success: false, count: 0, error: String(error)};
      }
    })()''', page)
    after = await browser.evaluate(expression, page)
    print('before=' + json.dumps({k: before.get(k) for k in ('url', 'title', 'hasSearchLabel', 'hasPlaceholder')}, ensure_ascii=False, default=str))
    print('apiProbe=' + json.dumps(apiProbe, ensure_ascii=False, default=str))
    print('afterSuccess=' + str(after.get('success')))
    print('hasDuckDuckGo=' + str(after.get('hasDuckDuckGo')))
    print('hasBing=' + str(after.get('hasBing')))
    print('hasUntrustedLabel=' + str(after.get('hasUntrustedLabel')))
    print('resultLinkCount=' + str(after.get('resultLinkCount')))


if __name__ == '__main__':
    asyncio.run(main())
