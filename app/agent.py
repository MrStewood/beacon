"""Agent loop — drives a model through tool calls until it produces a final answer.

Usage:
    from app.agent import run
    result = await run(
        system="You are a researcher...",
        user="What services does https://example.org provide?",
        tools=TOOLS,
    )
    print(result.content)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from app import llm as llm_mod

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

# Map of tool_name -> async callable(args: dict) -> str
_TOOL_HANDLERS: dict[str, Callable[[dict], Awaitable[str]]] = {}


def register(name: str, handler: Callable[[dict], Awaitable[str]]) -> None:
    _TOOL_HANDLERS[name] = handler


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    content: str
    steps: int
    tool_calls: list[dict] = field(default_factory=list)
    truncated: bool = False   # True if max_steps was hit


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def run(
    system: str,
    user: str,
    tools: list[dict],
    *,
    model: str = llm_mod.FLASH,
    max_steps: int = 20,
    extra_messages: list[dict] | None = None,
    extra_handlers: dict[str, Callable[[dict], Awaitable[str]]] | None = None,
) -> AgentResult:
    """Run the model in a tool loop until it stops calling tools.

    Args:
        system:         System prompt.
        user:           Initial user message.
        tools:          OpenAI-format tool schemas.
        model:          Model alias (default: flash).
        max_steps:      Hard cap on tool-call rounds.
        extra_messages: Prepend after system, before user (e.g. few-shot examples).
        extra_handlers: Per-run handlers that override/extend the global registry.
                        Use for BrowserSession and SearchSession tool binding.
    """
    messages: list[dict] = [{"role": "system", "content": system}]
    if extra_messages:
        messages.extend(extra_messages)
    messages.append({"role": "user", "content": user})

    recorded_calls: list[dict] = []

    for step in range(max_steps):
        log.debug("step %d — %d messages in context", step + 1, len(messages))

        response = await llm_mod.call(model, messages, tools=tools)
        msg = response.choices[0].message

        # Append assistant turn (tool_calls or content)
        messages.append(msg.model_dump(exclude_unset=True))

        # No more tool calls — model is done
        if not msg.tool_calls:
            return AgentResult(
                content=msg.content or "",
                steps=step + 1,
                tool_calls=recorded_calls,
            )

        # Execute each requested tool
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                args = {}
                log.warning("bad tool args for %s: %s", fn_name, e)

            log.info("→ tool: %s(%s)", fn_name, _fmt_args(args))
            recorded_calls.append({"tool": fn_name, "args": args})

            _handlers = {**_TOOL_HANDLERS, **(extra_handlers or {})}
            handler = _handlers.get(fn_name)
            if handler is None:
                result_str = f"[error: unknown tool '{fn_name}']"
            else:
                try:
                    result_str = await handler(args)
                except Exception as exc:
                    result_str = f"[tool error: {exc}]"
                    log.exception("tool %s raised", fn_name)

            log.debug("← %s: %d chars", fn_name, len(result_str))
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

    # Hit max_steps — return whatever the last content was
    last_content = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "assistant"),
        "",
    )
    return AgentResult(
        content=last_content or "[max steps reached]",
        steps=max_steps,
        tool_calls=recorded_calls,
        truncated=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = str(v)
        parts.append(f"{k}={s[:60]!r}" if len(s) > 60 else f"{k}={v!r}")
    return ", ".join(parts)
