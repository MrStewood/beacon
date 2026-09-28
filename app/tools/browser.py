"""Browser tools — stateless fast fetch + stateful interactive session.

fetch_page(url)      — stateless: plain HTTP → Playwright fallback. Fast.
BrowserSession       — stateful: persistent browser context with full
                       interaction support (click, fill, submit, scroll, etc.)
                       Apply stealth once at context creation; reuse across
                       all tool calls within a research run.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import Stealth

log = logging.getLogger(__name__)
# Domains the model must NOT navigate to — use the search() tool instead
_SEARCH_ENGINE_DOMAINS = {
    "google.com", "www.google.com",
    "bing.com", "www.bing.com",
    "duckduckgo.com", "www.duckduckgo.com",
    "search.yahoo.com", "yahoo.com",
    "yandex.com", "baidu.com",
    "webcache.googleusercontent.com",
}


# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_STEALTH = Stealth(
    navigator_user_agent_override=_UA,
    navigator_platform_override="Win32",
    navigator_languages_override=("en-US", "en"),
    chrome_runtime=False,  # OFF avoids a known detection vector in headless
)

_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--disable-gpu",
    "--no-first-run",
    "--no-zygote",
    "--disable-infobars",
    "--window-size=1920,1080",
]

_INIT_SCRIPT = """
    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
    delete Object.getPrototypeOf(navigator).webdriver;
"""

# Cookie/consent banner selectors — tried in order on every page load
_CONSENT_SELECTORS = [
    # OneTrust
    "#onetrust-accept-btn-handler",
    ".onetrust-accept-btn-handler",
    # Cookiebot
    "#CybotCookiebotDialogBodyButtonAccept",
    # Quantcast
    ".qc-cmp2-summary-buttons button:first-child",
    # Generic by text (Playwright syntax)
    "button:has-text('Accept All')",
    "button:has-text('Accept Cookies')",
    "button:has-text('Accept all cookies')",
    "button:has-text('I Accept')",
    "button:has-text('Agree and Continue')",
    "button:has-text('Agree')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    "button:has-text('Close')",
    "[aria-label='Accept cookies']",
    "[data-action='accept']",
    ".cc-accept",
    "#accept-cookies",
]

_PLAIN_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
}

# Per-domain page-load cap within a single session (courtesy limit)
_DOMAIN_PAGE_CAP = 8

# Max text returned per tool call (keep context window manageable)
_TEXT_CAP = 10_000


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "img",
                     "head", "footer", "nav", "iframe", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    text = "\n".join(lines)
    if len(text) > _TEXT_CAP:
        text = text[:_TEXT_CAP] + "\n\n[content truncated — use scroll_down or navigate to sub-page]"
    return text


# ---------------------------------------------------------------------------
# Stateless fast fetch (single URL, no session state)
# ---------------------------------------------------------------------------

async def fetch_page(
    url: str,
    *,
    force_browser: bool = False,
    screenshot_path: Optional[Path] = None,
) -> dict:
    """Stateless single-page fetch. Opens and closes browser each call."""
    if not force_browser:
        try:
            r = requests.get(url, headers=_PLAIN_HEADERS, timeout=15, allow_redirects=True)
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "text/html" in ct or "text/plain" in ct:
                text = _extract_text(r.text)
                if len(text) > 200:
                    return {"url": url, "method": "plain", "text": text, "ok": True, "error": None}
        except Exception:
            pass

    # Playwright fallback
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=_UA,
            locale="en-US",
            timezone_id="America/New_York",
        )
        await _STEALTH.apply_stealth_async(context)
        page = await context.new_page()
        await page.add_init_script(_INIT_SCRIPT)

        try:
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(random.uniform(0.8, 1.8))

            if screenshot_path:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path), full_page=True)

            text = _extract_text(await page.content())
            return {"url": url, "method": "browser", "text": text, "ok": True, "error": None}
        except Exception as exc:
            return {"url": url, "method": "browser", "text": "", "ok": False, "error": str(exc)}
        finally:
            await browser.close()


# ---------------------------------------------------------------------------
# Stateful BrowserSession
# ---------------------------------------------------------------------------

class BrowserSession:
    """Persistent browser context for interactive multi-step research.

    Keeps one browser + context + page alive across all tool calls in a
    research run. Apply stealth once; reuse for every navigation.

    Usage:
        async with BrowserSession(evidence_dir=Path("leads/runs/40744/evidence")) as s:
            handlers = s.handlers()
            schemas  = s.schemas()
            # pass handlers + schemas to agent.run()

    Domain courtesy cap: raises after _DOMAIN_PAGE_CAP loads per domain so
    we don't hammer a single site. Does not apply to navigate() calls that
    cross to a different domain.
    """

    def __init__(self, *, evidence_dir: Optional[Path] = None):
        self._evidence_dir = evidence_dir or Path("leads/evidence")
        self._pw = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._domain_hits: dict[str, int] = defaultdict(int)
        self._screenshot_n = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "BrowserSession":
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=_UA,
            locale="en-US",
            timezone_id="America/New_York",
            permissions=[],
        )
        await _STEALTH.apply_stealth_async(self._context)
        self._page = await self._context.new_page()
        await self._page.add_init_script(_INIT_SCRIPT)
        log.debug("BrowserSession started")
        return self

    async def __aexit__(self, *_) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        log.debug("BrowserSession closed")

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> str:
        """Go to URL. Returns page text. Auto-dismisses cookie banners."""
        domain = _domain(url)

        if domain in _SEARCH_ENGINE_DOMAINS:
            return (
                f"[BLOCKED] Do not navigate to search engines ({domain}). "
                "Use the search() tool — it routes through SearXNG and avoids "
                "bot detection and rate-limiting on search engines."
            )

        if self._domain_hits[domain] >= _DOMAIN_PAGE_CAP:
            return (
                f"[DOMAIN CAP] Already loaded {_DOMAIN_PAGE_CAP} pages from {domain}. "
                "Move to a different source."
            )

        await asyncio.sleep(random.uniform(1.0, 2.5))
        try:
            await self._page.goto(url, wait_until="networkidle", timeout=30_000)
        except Exception:
            # networkidle times out on some SPAs — fall back to domcontentloaded
            try:
                await self._page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                await asyncio.sleep(2.0)
            except Exception as exc:
                return f"[NAVIGATE ERROR] {exc}"

        self._domain_hits[domain] += 1
        await asyncio.sleep(random.uniform(0.5, 1.2))
        await self._auto_dismiss_consent()
        return await self._page_text()

    async def click(self, text: str) -> str:
        """Click an element by its visible text or aria-label. Returns page text."""
        page = self._page
        # Strategy 1: exact visible text on link/button
        for role in ("link", "button", "menuitem", "tab"):
            try:
                loc = page.get_by_role(role, name=text)
                if await loc.count() > 0:
                    await loc.first.click()
                    await asyncio.sleep(random.uniform(0.8, 1.5))
                    await self._wait_stable()
                    return await self._page_text()
            except Exception:
                pass

        # Strategy 2: partial text match anywhere
        try:
            loc = page.get_by_text(text, exact=False)
            if await loc.count() > 0:
                await loc.first.click()
                await asyncio.sleep(random.uniform(0.8, 1.5))
                await self._wait_stable()
                return await self._page_text()
        except Exception:
            pass

        # Strategy 3: CSS selector (if caller passed one)
        try:
            await page.click(text, timeout=3000)
            await asyncio.sleep(random.uniform(0.8, 1.5))
            return await self._page_text()
        except Exception:
            pass

        return f"[CLICK FAILED] Could not find clickable element matching: {text!r}"

    async def fill(self, label: str, value: str) -> str:
        """Fill an input field identified by label text or placeholder.
        Returns confirmation (does not submit)."""
        page = self._page
        # Strategy 1: by label
        try:
            loc = page.get_by_label(label, exact=False)
            if await loc.count() > 0:
                await loc.first.fill(value)
                return f"Filled '{label}' with {value!r}"
        except Exception:
            pass

        # Strategy 2: by placeholder
        try:
            loc = page.get_by_placeholder(label, exact=False)
            if await loc.count() > 0:
                await loc.first.fill(value)
                return f"Filled placeholder '{label}' with {value!r}"
        except Exception:
            pass

        # Strategy 3: CSS/role
        try:
            await page.fill(label, value)
            return f"Filled '{label}' with {value!r}"
        except Exception as exc:
            return f"[FILL FAILED] {exc}"

    async def submit(self) -> str:
        """Press Enter on the focused element (submits most forms)."""
        try:
            await self._page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(1.0, 2.0))
            await self._wait_stable()
            return await self._page_text()
        except Exception as exc:
            return f"[SUBMIT FAILED] {exc}"

    async def scroll_down(self) -> str:
        """Scroll down one viewport. Returns any new content revealed."""
        try:
            before = await self._page.evaluate("document.body.scrollHeight")
            await self._page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(random.uniform(0.8, 1.5))
            after = await self._page.evaluate("document.body.scrollHeight")
            text = await self._page_text()
            if after > before:
                return f"[Scrolled — page grew {after - before}px]\n\n{text}"
            return f"[Scrolled — no new content loaded]\n\n{text}"
        except Exception as exc:
            return f"[SCROLL FAILED] {exc}"

    async def get_links(self) -> str:
        """Return all visible links on the current page as a numbered list."""
        try:
            links = await self._page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const r = a.getBoundingClientRect();
                        return r.width > 0 && r.height > 0 && a.innerText.trim();
                    })
                    .slice(0, 60)
                    .map(a => ({
                        text: a.innerText.trim().replace(/\\s+/g, ' ').slice(0, 80),
                        href: a.href
                    }))
            """)
            if not links:
                return "[No visible links found]"
            lines = [f"{i+1}. {l['text']}\n   {l['href']}" for i, l in enumerate(links)]
            return "\n".join(lines)
        except Exception as exc:
            return f"[GET_LINKS FAILED] {exc}"

    async def screenshot(self, label: str = "") -> str:
        """Capture full-page screenshot. Returns the saved file path (use as evidence)."""
        self._screenshot_n += 1
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") if label else "page"
        fname = f"{self._screenshot_n:03d}-{slug}.png"
        path = self._evidence_dir / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self._page.screenshot(path=str(path), full_page=True)
            log.info("screenshot → %s", path)
            return f"Screenshot saved: {path}"
        except Exception as exc:
            return f"[SCREENSHOT FAILED] {exc}"

    async def dismiss_popup(self) -> str:
        """Attempt to dismiss cookie/consent banners or modal overlays."""
        result = await self._auto_dismiss_consent()
        if result:
            return f"Dismissed popup: {result}"
        return "[No popup found or already dismissed]"

    async def go_back(self) -> str:
        """Navigate back in browser history. Returns page text."""
        try:
            await self._page.go_back(wait_until="networkidle", timeout=15_000)
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return await self._page_text()
        except Exception as exc:
            return f"[GO_BACK FAILED] {exc}"

    async def current_url(self) -> str:
        """Return the current page URL."""
        return self._page.url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _page_text(self) -> str:
        url = self._page.url
        html = await self._page.content()
        text = _extract_text(html)
        return f"[PAGE: {url}]\n\n{text}"

    async def _wait_stable(self) -> None:
        """Wait for network to settle after an interaction."""
        try:
            await self._page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass  # timeout is fine; content may already be loaded

    async def _auto_dismiss_consent(self) -> Optional[str]:
        """Try each consent selector silently. Returns matched selector or None."""
        for sel in _CONSENT_SELECTORS:
            try:
                loc = self._page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click()
                    await asyncio.sleep(0.5)
                    log.debug("dismissed consent: %s", sel)
                    return sel
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # Tool registry interface
    # ------------------------------------------------------------------

    def handlers(self) -> dict:
        """Returns {tool_name: async_handler} bound to this session."""
        return {
            "navigate":      lambda a: self.navigate(a["url"]),
            "click":         lambda a: self.click(a["text"]),
            "fill":          lambda a: self.fill(a["label"], a["value"]),
            "submit":        lambda a: self.submit(),
            "scroll_down":   lambda a: self.scroll_down(),
            "get_links":     lambda a: self.get_links(),
            "screenshot":    lambda a: self.screenshot(a.get("label", "")),
            "dismiss_popup": lambda a: self.dismiss_popup(),
            "go_back":       lambda a: self.go_back(),
        }

    @staticmethod
    def schemas() -> list[dict]:
        return SESSION_TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# Tool schemas for the interactive session
# ---------------------------------------------------------------------------

SESSION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Go to a URL. Returns the page text. Use for the first load of any site or sub-page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL (https://...)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click a link or button by its visible text. Use the exact label you see on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Visible text of the element to click"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill",
            "description": "Type a value into a form field. Identify the field by its label or placeholder text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Field label or placeholder text"},
                    "value": {"type": "string", "description": "Value to type"},
                },
                "required": ["label", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit",
            "description": "Submit the current form by pressing Enter. Use after fill().",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_down",
            "description": "Scroll the page down one screen. Use when content appears cut off or lazy-loaded.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_links",
            "description": "List all visible links on the current page with their text and URLs. Use to find which sub-page to visit next.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Save a screenshot of the current page as evidence. Use when you find contact info, hours, or services.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Short label for the filename (e.g. 'contact-page', 'hours')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dismiss_popup",
            "description": "Dismiss a cookie consent banner or modal overlay blocking the page.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "go_back",
            "description": "Navigate back to the previous page (like the browser back button).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return url
