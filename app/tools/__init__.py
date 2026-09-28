"""Tool registry — import this to register all tools with the agent loop."""

from __future__ import annotations
from app import agent
from app.tools import browser as _browser


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------

async def _handle_fetch_page(args: dict) -> str:
    result = await _browser.fetch_page(
        args["url"],
        force_browser=args.get("force_browser", False),
    )
    prefix = f"[{result['method'].upper()} {result['url']}]\n\n"
    return prefix + (result["text"] if result["ok"] else f"ERROR: {result['error']}")


agent.register("fetch_page", _handle_fetch_page)

FETCH_PAGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fetch_page",
        "description": (
            "Fetch a URL and return its readable text content. "
            "Uses fast plain HTTP first; automatically falls back to a "
            "stealth headless browser for JS-heavy or bot-protected pages. "
            "Use force_browser=true to skip straight to browser."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL including scheme (https://...)",
                },
                "force_browser": {
                    "type": "boolean",
                    "description": "Skip plain HTTP and go straight to browser. "
                                   "Use when plain HTTP is known to fail (SPAs, Cloudflare, etc.)",
                },
            },
            "required": ["url"],
        },
    },
}

# All available tool schemas for passing to the agent
ALL_TOOLS = [FETCH_PAGE_SCHEMA]
