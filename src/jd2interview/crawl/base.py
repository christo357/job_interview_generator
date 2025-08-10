from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional
import aiohttp
import time

DEFAULT_HEADERS = {
    "User-Agent": "jd2interview-crawler/0.1 (+research; contact: you@example.com)"
}

class Fetcher(ABC):
    """Abstract interface for crawl sources."""
    name: str

    @abstractmethod
    async def fetch(self, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """Yield raw provider items (dicts)."""

class RateLimiter:
    def __init__(self, rate_per_sec: float = 2.0):
        self.delay = 1.0 / max(rate_per_sec, 0.1)
        self._last = 0.0
    async def wait(self):
        now = time.time()
        delta = now - self._last
        if delta < self.delay:
            await asyncio.sleep(self.delay - delta)
        self._last = time.time()

class HttpClient:
    def __init__(self, headers: Optional[Dict[str,str]] = None, timeout: int = 30):
        self.headers = headers or DEFAULT_HEADERS
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers, timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self
    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()
    async def get_json(self, url: str, params: Dict[str, Any] | None = None) -> Any:
        assert self.session, "HttpClient not started"
        async with self.session.get(url, params=params) as r:
            r.raise_for_status()
            return await r.json()