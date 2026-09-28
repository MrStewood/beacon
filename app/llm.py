"""Thin async wrapper around the LiteLLM proxy.

Usage:
    from app.llm import flash, mimo
    response = await flash([{"role":"user","content":"hello"}])
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from dotenv import load_dotenv  # optional; falls back to env vars

# Load .env from repo root (non-fatal if missing)
_ENV = Path(__file__).resolve().parent.parent / ".env"
if _ENV.exists():
    load_dotenv(_ENV)

_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://100.73.139.50:4000/v1")
_API_KEY  = os.environ.get("LITELLM_MASTER_KEY", "")

_client = AsyncOpenAI(base_url=_BASE_URL, api_key=_API_KEY)

# ---------------------------------------------------------------------------
# Model aliases
# ---------------------------------------------------------------------------

FLASH = "flash"   # deepseek-v4.1-flash — fast, research + extraction
MIMO  = "mimo"    # mimo-v2.5           — careful, verification


# ---------------------------------------------------------------------------
# Core call
# ---------------------------------------------------------------------------

async def call(
    model: str,
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    response_format: dict | None = None,
) -> Any:
    """Raw completion call. Returns the full response object."""
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    if response_format:
        kwargs["response_format"] = response_format
    return await _client.chat.completions.create(**kwargs)


async def flash(messages: list[dict], **kwargs) -> Any:
    return await call(FLASH, messages, **kwargs)


async def mimo(messages: list[dict], **kwargs) -> Any:
    return await call(MIMO, messages, **kwargs)


async def embed(text: str | list[str]) -> list[list[float]]:
    """1024-dim embeddings via mistral-embed."""
    inputs = [text] if isinstance(text, str) else text
    r = await _client.embeddings.create(model="mistral-embed", input=inputs)
    return [item.embedding for item in r.data]
