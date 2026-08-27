"""SCP V3.1 Web Navigator.

Browser access is opt-in. Public pages can be fetched directly; logged-in
pages require a user-provided local DevTools session. No credentials are read.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

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
        """Read a public page without bypassing the canonical SSRF policy.

        Redirects are handled explicitly so every destination is validated;
        httpx must not silently follow a redirect into a private network. The
        response body is streamed with a bounded byte budget before decoding.
        """
        current_url = self.browser.validate_url(url)
        max_chars = max(1, min(int(max_chars), 1_000_000))
        max_bytes = max_chars * 4
        redirect_statuses = {301, 302, 303, 307, 308}

        async with httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            timeout=20,
            headers={"User-Agent": "SCP-DNA-WebNavigator/3.1"},
        ) as client:
            for _ in range(5):
                current_url = self.browser.validate_url(current_url)
                async with client.stream("GET", current_url) as response:
                    if response.status_code in redirect_statuses:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Redirect response has no Location header")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > max_bytes:
                        raise ValueError("Response exceeds public browse size limit")

                    chunks: list[bytes] = []
                    total_bytes = 0
                    async for chunk in response.aiter_bytes():
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise ValueError("Response exceeds public browse size limit")
                        chunks.append(chunk)

                    encoding = response.encoding or "utf-8"
                    text = b"".join(chunks).decode(encoding, errors="replace")[:max_chars]
                    final_url = str(response.url)
                    status = response.status_code
                    content_type = response.headers.get("content-type", "")
                    break
            else:
                raise ValueError("Too many redirects")

        return {
            "success": True,
            "url": final_url,
            "status": status,
            "contentType": content_type,
            "text": text,
            "method": "public-http-read",
            "timestamp": time.time(),
        }

    async def search_public(self, query: str, max_results: int = 10) -> dict[str, Any]:
        return await self.search_engine.search(query, max_results=max_results)

    async def browse_logged_in(self, url: str) -> dict[str, Any]:
        return await self.browser.navigate_and_read(url)

    async def browse(self, url: str, use_logged_in_browser: bool = False) -> dict[str, Any]:
        if use_logged_in_browser:
            return await self.browse_logged_in(url)
        return await self.browse_public(url)
