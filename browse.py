#!/usr/bin/env python3
"""Test: prompt + URL using a full interactive browser session.

Usage:
    # Single page read (stateless fast path)
    python3 browse.py "What services does this org offer?" https://example.com

    # Interactive session (follows links, fills forms, uses search)
    python3 browse.py --session "Find phone, address, and hours" https://example.com

    # With search enabled
    python3 browse.py --session --search "What food banks serve Laurel County KY?"
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import app.tools  # register stateless tools
from app.agent import run
from app.tools import BrowserSession, SearchSession, session_tools
from app.tools import FETCH_PAGE_SCHEMA

SYSTEM_STATELESS = """\
You are a community resource researcher. Fetch the given URL and answer \
based only on what you find. Be concise and factual. If information is \
not on the page, say so.\
"""

SYSTEM_SESSION = """\
You are a community resource researcher investigating a website.
You have browser tools to navigate, click links, fill forms, scroll, \
and take screenshots.

Rules:
- Navigate to the URL first, then explore sub-pages as needed.
- Use get_links() to see what pages are available before clicking.
- Use screenshot() whenever you find contact info, hours, or services — \
  these are evidence.
- Use go_back() to return to a directory after reading a resource page.
- Stop when you have found: name, phone, address, hours, services, eligibility.
- If a popup blocks the page, use dismiss_popup() first.\
"""

SYSTEM_WITH_SEARCH = SYSTEM_SESSION + """
- Use search() for additional context or to verify facts found on the page.
- Keep searches targeted: include city, county, and state in every query.
- Don't repeat a search you've already done.\
"""


async def run_stateless(prompt: str, url: str) -> None:
    from app.tools import FETCH_PAGE_SCHEMA
    result = await run(
        system=SYSTEM_STATELESS,
        user=f"{prompt}\n\nURL: {url}",
        tools=[FETCH_PAGE_SCHEMA],
    )
    _print_result(result)


async def run_session(prompt: str, url: str, with_search: bool = False) -> None:
    evidence_dir = Path("leads/evidence")

    async with BrowserSession(evidence_dir=evidence_dir) as browser:
        async with SearchSession() as search:
            schemas, handlers = session_tools(browser, search)

            # For stateless-only, trim search schema if not wanted
            if not with_search:
                schemas = [s for s in schemas if s["function"]["name"] != "search"]
                handlers.pop("search", None)

            user_msg = f"{prompt}\n\nStart at: {url}" if url else prompt

            result = await run(
                system=SYSTEM_WITH_SEARCH if with_search else SYSTEM_SESSION,
                user=user_msg,
                tools=schemas,
                extra_handlers=handlers,
                max_steps=30,
            )
            _print_result(result)


def _print_result(result) -> None:
    print("\n" + "─" * 60)
    print(result.content)
    print("─" * 60)
    print(f"\nSteps: {result.steps}  |  Tool calls: {len(result.tool_calls)}")
    for tc in result.tool_calls:
        args_short = {k: (str(v)[:50] + "…" if len(str(v)) > 50 else v)
                      for k, v in tc["args"].items()}
        print(f"  • {tc['tool']}({args_short})")
    if result.truncated:
        print("  ⚠ max_steps reached")


async def main() -> None:
    args = sys.argv[1:]
    use_session = "--session" in args
    use_search  = "--search"  in args
    args = [a for a in args if not a.startswith("--")]

    if use_search and not args:
        # Search-only mode: no URL needed
        prompt = args[0] if args else "Search for food banks in Laurel County KY"
        await run_session(prompt, url="", with_search=True)
        return

    if len(args) < 2:
        print("Usage: browse.py [--session] [--search] <prompt> <url>")
        print("       browse.py --session --search <prompt>  (search without starting URL)")
        sys.exit(1)

    prompt, url = args[0], args[1]
    print(f"\nPrompt : {prompt}")
    print(f"URL    : {url or '(none)'}")
    print(f"Mode   : {'session+search' if use_search else 'session' if use_session else 'stateless'}\n")

    if use_session or use_search:
        await run_session(prompt, url, with_search=use_search)
    else:
        await run_stateless(prompt, url)


if __name__ == "__main__":
    asyncio.run(main())
