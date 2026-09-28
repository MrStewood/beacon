"""Stealth browser tool — fetches pages evading bot detection.

Tries plain HTTP first (fast, no fingerprint risk).
Falls back to Playwright with full stealth suite on JS-heavy or blocked pages.
"""

from __future__ import annotations

import asyncio
import random
import re
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Realistic Chrome 124 on Windows user agent — matches Playwright's bundled Chromium
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_STEALTH = Stealth(
    navigator_user_agent_override=_UA,
    navigator_platform_override="Win32",
    navigator_languages_override=("en-US", "en"),
    # Keep chrome_runtime OFF — exposes real Chrome and confuses headless detection
    chrome_runtime=False,
    # All other evasions on (defaults)
)

_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--window-size=1920,1080",
    # Suppress automation infobar
    "--disable-infobars",
    # Realistic hardware concurrency
    "--renderer-process-limit=4",
]

_PLAIN_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_PLAIN_TIMEOUT = 15  # seconds
_JS_TIMEOUT_MS = 30_000  # ms for Playwright


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_text(html: str, url: str = "") -> str:
    """Strip tags; return clean readable text, ≤ 12 000 chars."""
    soup = BeautifulSoup(html, "html.parser")

    # Drop noise elements
    for tag in soup(["script", "style", "noscript", "svg", "img",
                     "head", "footer", "nav", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # Collapse blank lines
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    text = "\n".join(lines)

    # Cap to avoid blowing context window
    if len(text) > 12_000:
        text = text[:12_000] + "\n\n[content truncated]"

    return text


# ---------------------------------------------------------------------------
# Plain HTTP fetch (fast path)
# ---------------------------------------------------------------------------

def _fetch_plain(url: str) -> tuple[str, bool]:
    """Returns (text, success). Fast; no JS; no fingerprint."""
    try:
        r = requests.get(url, headers=_PLAIN_HEADERS,
                         timeout=_PLAIN_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "text/html" not in ct and "text/plain" not in ct:
            return f"[non-HTML content-type: {ct}]", False
        return _extract_text(r.text, url), True
    except Exception as exc:
        return str(exc), False


# ---------------------------------------------------------------------------
# Playwright stealth fetch (fallback)
# ---------------------------------------------------------------------------

async def _fetch_playwright(url: str, screenshot_path: Optional[Path] = None) -> tuple[str, bool]:
    """Headless Chromium with full stealth suite."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=_LAUNCH_ARGS,
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=_UA,
            locale="en-US",
            timezone_id="America/New_York",
            # Suppress WebRTC leak
            permissions=[],
        )

        # Apply all stealth patches to the context
        await _STEALTH.apply_stealth_async(context)

        page = await context.new_page()

        # Extra JS patches that stealth doesn't cover
        await page.add_init_script("""
            // Mask headless: make plugins non-empty
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            // Mask headless: languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            // Remove the automation flag entirely
            delete Object.getPrototypeOf(navigator).webdriver;
        """)

        try:
            # Human-like: slight random delay before navigation
            await asyncio.sleep(random.uniform(0.5, 1.5))

            await page.goto(url, wait_until="networkidle",
                            timeout=_JS_TIMEOUT_MS)

            # Wait a beat for lazy-loaded content
            await asyncio.sleep(random.uniform(0.8, 1.8))

            if screenshot_path:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path), full_page=True)

            html = await page.content()
            return _extract_text(html, url), True

        except Exception as exc:
            return f"[playwright error: {exc}]", False
        finally:
            await browser.close()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def fetch_page(
    url: str,
    *,
    force_browser: bool = False,
    screenshot_path: Optional[Path] = None,
) -> dict:
    """Fetch a URL and return clean text content.

    Returns:
        {
            "url": str,
            "method": "plain" | "browser",
            "text": str,
            "ok": bool,
            "error": str | None,
        }
    """
    # Plain HTTP fast path (skip for known JS-heavy domains or if forced)
    if not force_browser:
        text, ok = _fetch_plain(url)
        if ok and len(text) > 200:
            return {"url": url, "method": "plain", "text": text, "ok": True, "error": None}

    # Playwright fallback
    text, ok = await _fetch_playwright(url, screenshot_path=screenshot_path)
    return {
        "url": url,
        "method": "browser",
        "text": text,
        "ok": ok,
        "error": None if ok else text,
    }
