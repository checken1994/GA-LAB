"""SCP V3.1 Web Navigator.

Browser access is opt-in. Public pages can be fetched directly; logged-in
pages require a user-provided local DevTools session. No credentials are read.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from .browser_session import BrowserSession
from .internet_search import InternetSearch


class WebNavigator:
    def __init__(self, browser: BrowserSession | None = None, search: InternetSearch | None = None) -> None:
        self.browser = browser or BrowserSession()
        self.search_engine = search or InternetSearch()

    async def status(self) -> dict[str, Any]:
        browser_status = await self.browser.status()
        return {"navigator": "online", "browserSession": browser_status, "policy": "public-read or explicit local browser session"}

    async def browse_public(self, url: str, max_chars: int = 100_000) -> dict[str, Any]:
        url = self.browser.validate_url(url)
        async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers={"User-Agent": "SCP-DNA-WebNavigator/3.1"}) as client:
            response = await client.get(url)
            response.raise_for_status()
            text = response.text[:max_chars]
        return {"success": True, "url": str(response.url), "status": response.status_code, "contentType": response.headers.get("content-type", ""), "text": text, "method": "public-http-read", "timestamp": time.time()}

    async def search_public(self, query: str, max_results: int = 10) -> dict[str, Any]:
        return await self.search_engine.search(query, max_results=max_results)

    async def browse_logged_in(self, url: str) -> dict[str, Any]:
        return await self.browser.navigate_and_read(url)

    async def browse(self, url: str, use_logged_in_browser: bool = False) -> dict[str, Any]:
        if use_logged_in_browser:
            return await self.browse_logged_in(url)
        return await self.browse_public(url)
