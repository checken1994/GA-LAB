from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.web_control.internet_search import InternetSearch


async def main() -> None:
    result = await InternetSearch().search('SCP self correcting process', max_results=5)
    print('success=' + str(result.get('success')))
    print('providers=' + ','.join(result.get('providersTried', [])))
    print('resultCount=' + str(len(result.get('results', []))))
    for index, item in enumerate(result.get('results', [])):
        print('result' + str(index) + '=' + json.dumps({
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'provider': item.get('provider', '')
        }, ensure_ascii=False))
    if result.get('errors'):
        print('errors=' + json.dumps(result['errors'], ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
