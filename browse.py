#!/usr/bin/env python3
"""Minimal test: pass a prompt + URL and let the agent browse.

Usage:
    python3 browse.py "What services does this org offer?" https://example.com
    python3 browse.py "Find the phone number and address" https://some-nonprofit.org
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import app.tools  # registers all tools
from app.agent import run
from app.tools import ALL_TOOLS

SYSTEM = """\
You are a community resource researcher. When given a prompt and a URL, \
fetch the page and answer based only on what you find there. \
Be concise and factual. If information is not on the page, say so.\
"""

async def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: browse.py <prompt> <url>")
        sys.exit(1)

    prompt = sys.argv[1]
    url    = sys.argv[2]

    print(f"\nPrompt : {prompt}")
    print(f"URL    : {url}\n")

    result = await run(
        system=SYSTEM,
        user=f"{prompt}\n\nURL: {url}",
        tools=ALL_TOOLS,
    )

    print("─" * 60)
    print(result.content)
    print("─" * 60)
    print(f"\nSteps: {result.steps}  |  Tool calls: {len(result.tool_calls)}")
    for tc in result.tool_calls:
        print(f"  • {tc['tool']}({tc['args']})")


if __name__ == "__main__":
    asyncio.run(main())
