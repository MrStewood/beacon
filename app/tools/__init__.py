"""Tool registry.

Stateless tools (fetch_page) are registered globally.
Session tools (navigate, click, fill, etc.) are registered per-run via
BrowserSession.handlers() — see app/tools/browser.py.
"""

from __future__ import annotations

from app import agent
from app.tools.browser import BrowserSession, fetch_page
from app.tools.search import SEARCH_SCHEMA, SearchSession, make_search_handler

# ---------------------------------------------------------------------------
# Stateless fetch_page (global — no session required)
# ---------------------------------------------------------------------------

async def _handle_fetch_page(args: dict) -> str:
    result = await fetch_page(
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
            "Fetch a single URL and return its text. Fast stateless read — "
            "no cookies or session state carried between calls. "
            "Use for quick one-off reads. For interactive browsing "
            "(clicking, forms, navigation) use navigate/click/fill instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "force_browser": {
                    "type": "boolean",
                    "description": "Skip plain HTTP; go straight to headless browser.",
                },
            },
            "required": ["url"],
        },
    },
}

# ---------------------------------------------------------------------------
# Convenience: all tool schemas for a full research session
# ---------------------------------------------------------------------------

def session_tools(
    browser: BrowserSession,
    search: SearchSession,
) -> tuple[list[dict], dict]:
    """Build (schemas, handlers) for a complete research session.

    Returns:
        schemas:  list of OpenAI tool schemas to pass to agent.run()
        handlers: dict of {name: handler} to pass as extra_handlers to agent.run()
    """
    from app.tools.browser import SESSION_TOOL_SCHEMAS

    schemas = [FETCH_PAGE_SCHEMA, SEARCH_SCHEMA] + SESSION_TOOL_SCHEMAS

    handlers: dict = {
        "fetch_page": _handle_fetch_page,
        "search": make_search_handler(search),
        **browser.handlers(),
    }

    return schemas, handlers


# Re-export for convenience
__all__ = [
    "BrowserSession",
    "SearchSession",
    "session_tools",
    "FETCH_PAGE_SCHEMA",
    "SEARCH_SCHEMA",
]
