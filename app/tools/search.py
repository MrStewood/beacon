"""SearXNG search tool with rate limiting and best-practice protections.

One SearchSession per research run. Enforces:
  - Random inter-search delay (avoids pattern detection by upstream engines)
  - Per-session query cap (don't exhaust upstream engine quotas)
  - Duplicate query guard (don't re-run searches we already did)
  - Result dedup by URL (engines return overlapping results)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import time
from typing import Optional
from urllib.parse import urlencode, urlparse

import requests

log = logging.getLogger(__name__)

_SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")

# ---------------------------------------------------------------------------
# Rate limiting config
# ---------------------------------------------------------------------------

# Delay between successive searches — random within this range (seconds)
# Upstream engines start flagging at <2s consistent intervals.
_MIN_DELAY = 4.0
_MAX_DELAY = 9.0

# Hard cap on searches per session.
# A thorough ZIP research run needs ~15–25 searches across all categories.
_DEFAULT_SESSION_CAP = 50

# Timeout for SearXNG HTTP call (seconds)
_HTTP_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SearchLimitReached(Exception):
    """Raised when the session search cap is hit."""


class DuplicateQuery(Exception):
    """Raised when an identical query has already been run this session."""


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SearchSession:
    """Rate-limited SearXNG client. One instance per research run.

    Usage:
        async with SearchSession() as s:
            results = await s.search("Laurel County food bank Kentucky")
    """

    def __init__(
        self,
        *,
        base_url: str = _SEARXNG_URL,
        session_cap: int = _DEFAULT_SESSION_CAP,
        min_delay: float = _MIN_DELAY,
        max_delay: float = _MAX_DELAY,
    ):
        self._base_url = base_url.rstrip("/")
        self._cap = session_cap
        self._min = min_delay
        self._max = max_delay

        self._count = 0
        self._last_search_at: float = 0.0
        # Canonical query hash → result count (guard against duplicate queries)
        self._seen_queries: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Context manager (optional — session is also usable standalone)
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "SearchSession":
        return self

    async def __aexit__(self, *_) -> None:
        pass  # nothing to clean up; HTTP is stateless

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def searches_remaining(self) -> int:
        return self._cap - self._count

    @property
    def search_history(self) -> list[str]:
        return list(self._seen_queries.keys())

    async def search(
        self,
        query: str,
        *,
        category: str = "general",
        max_results: int = 10,
        time_range: Optional[str] = None,  # "day" | "week" | "month" | "year"
        engines: Optional[list[str]] = None,
        allow_duplicate: bool = False,
    ) -> list[dict]:
        """Search SearXNG. Returns list of result dicts.

        Args:
            query:          Natural language search query.
            category:       SearXNG category (general, news, social+media, map).
            max_results:    Cap returned results (SearXNG often returns 50–100).
            time_range:     Filter by recency (None = no filter).
            engines:        Specific engines to use (None = SearXNG default).
            allow_duplicate: If True, re-run a query we've already seen.

        Returns:
            [{"title", "url", "snippet", "engines", "score"}, ...]
        """
        key = _query_key(query, category)

        if not allow_duplicate and key in self._seen_queries:
            log.info("skipping duplicate query: %r", query)
            raise DuplicateQuery(f"Already searched: {query!r}")

        if self._count >= self._cap:
            raise SearchLimitReached(
                f"Session cap of {self._cap} searches reached. "
                f"Queries so far: {self._count}"
            )

        await self._rate_wait()

        log.info("search [%d/%d] %r (cat=%s)", self._count + 1, self._cap, query, category)

        params: dict = {
            "q": query,
            "format": "json",
            "categories": category,
            "language": "en",
            "safesearch": "0",
        }
        if time_range:
            params["time_range"] = time_range
        if engines:
            params["engines"] = ",".join(engines)

        try:
            r = requests.get(
                f"{self._base_url}/search",
                params=params,
                timeout=_HTTP_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            log.warning("search failed: %s", exc)
            return [{"error": str(exc)}]

        results = _parse_results(data, max_results)

        self._count += 1
        self._seen_queries[key] = len(results)
        log.debug("← %d results", len(results))
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _rate_wait(self) -> None:
        elapsed = time.monotonic() - self._last_search_at
        target = random.uniform(self._min, self._max)
        wait = target - elapsed
        if wait > 0:
            log.debug("rate-limit wait %.1fs", wait)
            await asyncio.sleep(wait)
        self._last_search_at = time.monotonic()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _query_key(query: str, category: str) -> str:
    canonical = f"{category}:{query.lower().strip()}"
    return hashlib.md5(canonical.encode()).hexdigest()


def _parse_results(data: dict, limit: int) -> list[dict]:
    out = []
    seen_urls: set[str] = set()

    for r in data.get("results", []):
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        out.append({
            "title":   r.get("title", ""),
            "url":     url,
            "snippet": r.get("content", ""),
            "engines": r.get("engines", [r.get("engine", "")]),
            "score":   r.get("score", 0),
        })

        if len(out) >= limit:
            break

    return out


# ---------------------------------------------------------------------------
# Tool schema + handler factory
# ---------------------------------------------------------------------------

def make_search_handler(session: SearchSession):
    """Returns an async handler bound to a SearchSession instance."""

    async def _handle_search(args: dict) -> str:
        query    = args["query"]
        category = args.get("category", "general")
        max_r    = min(int(args.get("max_results", 10)), 20)
        time_r   = args.get("time_range")
        engines  = args.get("engines")

        try:
            results = await session.search(
                query,
                category=category,
                max_results=max_r,
                time_range=time_r,
                engines=engines,
            )
        except SearchLimitReached as e:
            return f"[SEARCH LIMIT REACHED] {e}"
        except DuplicateQuery:
            return (
                f"[DUPLICATE QUERY] '{query}' was already searched this session. "
                f"Searches remaining: {session.searches_remaining}"
            )

        if not results:
            return f"No results for: {query!r}"

        if "error" in results[0]:
            return f"[SEARCH ERROR] {results[0]['error']}"

        lines = [
            f"Search: {query!r}  |  {len(results)} results  "
            f"|  {session.searches_remaining} searches remaining\n"
        ]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['url']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet'][:200]}")
            lines.append("")

        return "\n".join(lines)

    return _handle_search


SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search",
        "description": (
            "Search the web via SearXNG. Use specific, targeted queries. "
            "Each search costs against a session budget — don't repeat similar queries. "
            "Category 'general' for web results; 'news' for recent coverage; "
            "'social media' for Facebook/community pages; 'map' for location lookups."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query. Be specific: include city/county/state. "
                        "Good: 'Laurel County Kentucky food bank phone hours'. "
                        "Bad: 'food bank'."
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": ["general", "news", "social media", "map"],
                    "description": "Search category. Default: general.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (1–20). Default: 10.",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "description": "Filter by recency. Omit for no filter.",
                },
            },
            "required": ["query"],
        },
    },
}
