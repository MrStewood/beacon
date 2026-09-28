"""ZIP research pipeline — entry point.

Usage:
    python3 -m app.pipeline.research 40744
    python3 -m app.pipeline.research 40744 --dry-run   # validate only, no saves
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

BEACON_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BEACON_ROOT / "leads"))
sys.path.insert(0, str(BEACON_ROOT / "scripts"))

import research as _r

from app import agent
from app.tools import BrowserSession, SearchSession, session_tools
from app.pipeline.lead_store import LeadStore
from app.pipeline.prompts import (
    build_system_prompt,
    CREATE_LEAD_SCHEMA,
    CHECK_URL_SCHEMA,
)

log = logging.getLogger(__name__)


async def run_zip(zip_code: str, *, dry_run: bool = False) -> dict:
    """Run the full lead research pipeline for a ZIP code.

    Idempotent: safe to run multiple times on the same ZIP.
    - check_url() skips URLs already evaluated in prior runs
    - create_lead() rejects duplicates against all known sources
    - Only genuinely new resources are saved

    Args:
        zip_code: 5-digit ZIP code.
        dry_run:  If True, validate setup but make no LLM calls or writes.

    Returns:
        Summary dict with new_leads count, run_id, raw_file path.
    """
    zip_code = zip_code.strip().zfill(5)
    log.info("=== research run: ZIP %s ===", zip_code)

    # Resolve ZIP → county/state/city + need score
    zip_info = _r.resolve_zip(zip_code)

    # Enrich with need score from census data
    try:
        import json as _json
        needs_path = BEACON_ROOT / "data" / "census" / "needs-analysis.json"
        if needs_path.exists():
            needs = _json.loads(needs_path.read_text())
            z = needs.get("zip_analysis", {}).get(zip_code, {})
            zip_info["need_score"] = z.get("need_score", "unknown")
            zip_info["need_flag"]  = z.get("need_flag", "")
    except Exception:
        pass

    log.info("area: %s County, %s (ZIP %s)", zip_info["county"], zip_info["state"], zip_code)

    if dry_run:
        store = LeadStore(zip_code, zip_info)
        return {
            "dry_run": True,
            "zip": zip_code,
            "zip_info": zip_info,
            "context": store.context_summary(),
        }

    # Init lead store (loads all existing dedup indexes + seen_urls)
    store = LeadStore(zip_code, zip_info)
    context = store.context_summary()
    log.info("context: %s", context)

    # Build system prompt
    system = build_system_prompt(zip_info, context)

    # Build tool set: search + browser + create_lead + check_url
    evidence_dir = BEACON_ROOT / "leads" / "runs" / zip_code / "evidence"

    async with BrowserSession(evidence_dir=evidence_dir) as browser:
        async with SearchSession() as search:
            schemas, handlers = session_tools(browser, search)

            # Add pipeline-specific tools
            schemas = schemas + [CREATE_LEAD_SCHEMA, CHECK_URL_SCHEMA]
            handlers["create_lead"] = store.handle_create_lead
            handlers["check_url"]   = store.handle_check_url

            user_msg = (
                f"Research all 17 community resource categories for "
                f"ZIP {zip_code} ({zip_info['county']} County, {zip_info['state']}). "
                f"Save every valid resource immediately with create_lead()."
            )

            log.info("starting agent — %d tools, max 200 steps", len(schemas))
            result = await agent.run(
                system=system,
                user=user_msg,
                tools=schemas,
                extra_handlers=handlers,
                max_steps=200,
            )

    log.info("agent done in %d steps, %d tool calls", result.steps, len(result.tool_calls))

    # Summarize tool usage
    tool_counts: dict[str, int] = {}
    for tc in result.tool_calls:
        tool_counts[tc["tool"]] = tool_counts.get(tc["tool"], 0) + 1

    # Finalize: write run file + call research.py process + persist seen_urls
    finalize_result = store.finalize()

    summary = {
        "run_id":       store.run_id,
        "zip":          zip_code,
        "county":       zip_info["county"],
        "state":        zip_info["state"],
        "new_leads":    len(store.session_leads),
        "agent_steps":  result.steps,
        "truncated":    result.truncated,
        "tool_counts":  tool_counts,
        **finalize_result,
        "agent_summary": result.content,
    }

    _print_summary(summary)
    return summary


def _print_summary(s: dict) -> None:
    print("\n" + "=" * 60)
    print(f"ZIP {s['zip']} — {s['county']} County, {s['state']}")
    print(f"New leads: {s['new_leads']}")
    print(f"Agent steps: {s['agent_steps']}" + (" [TRUNCATED]" if s.get("truncated") else ""))
    print("\nTool usage:")
    for tool, n in sorted(s.get("tool_counts", {}).items(), key=lambda x: -x[1]):
        print(f"  {tool:<20} {n}")
    print("\nAgent summary:")
    print(s.get("agent_summary", ""))
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if not a.startswith("--")]

    if not args:
        print("Usage: python3 -m app.pipeline.research <zip> [--dry-run]")
        sys.exit(1)

    result = asyncio.run(run_zip(args[0], dry_run=dry_run))
    print(json.dumps(result, indent=2, default=str))
