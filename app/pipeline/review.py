"""
AI Duplicate Reviewer
=====================
Takes a processed run file (with a `needs_ai_review` bucket) and asks the
flash model to decide for each flagged pair: same_org or different_orgs.

Usage
-----
    python -m app.pipeline.review <processed_file.json>

    # Or in code:
    from app.pipeline.review import review_file
    results = asyncio.run(review_file(Path("leads/runs/40744/run-processed.json")))

Output
------
Writes a `-reviewed.json` file next to the input with each lead annotated with
a `review_decision` field:
    same_org          → confirmed duplicate; move to duplicates bucket
    different_orgs    → confirmed distinct; move to new_leads
    needs_investigation → AI not confident; human review required
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from app import llm

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a community resource directory quality-control specialist.
Your job is to determine whether two resource records refer to the same
real-world organization or service, or whether they are genuinely different.

Rules:
- Same name + same phone = almost certainly same_org.
- Same name + same address = almost certainly same_org.
- Different addresses of the same franchise/network (e.g. "Grace Health - Mountain View"
  vs "Grace Health - Bishop Street") = different_orgs (they serve different people).
- A parent org and one of its programs (e.g. "Daniel Boone CAA" vs "Daniel Boone CAA LIHEAP")
  = different_orgs (they are distinct services even if same entity).
- Shared domain only, different names, different addresses = different_orgs.
- When genuinely uncertain, use needs_investigation.

Respond ONLY with valid JSON, no markdown, no explanation:
{"decision": "same_org"|"different_orgs"|"needs_investigation", "reason": "<one sentence>"}
"""

_USER_TEMPLATE = """\
## Candidate (newly found lead)
{candidate}

## Existing (already in system)
{existing}

## Match signal
{match_type} — matched on: {matched_fields}

Are these the same organization / service?
"""


def _fmt(record: dict) -> str:
    fields = ["name", "category", "address", "city", "state", "zip",
              "phone", "phones", "url", "description"]
    lines = []
    for f in fields:
        v = record.get(f)
        if v:
            lines.append(f"  {f}: {v}")
    return "\n".join(lines) or "  (no details)"


# ---------------------------------------------------------------------------
# Core reviewer
# ---------------------------------------------------------------------------

async def review_pair(candidate: dict, existing_name: str, match_type: str,
                      matched_fields: list[str]) -> dict:
    """Ask the model about one pair. Returns the candidate annotated with decision."""
    # Build a fake existing record from the match info — we only have name + match type
    # in the flag. The existing record's details come from what was stored.
    existing_stub = {"name": existing_name}

    user_msg = _USER_TEMPLATE.format(
        candidate=_fmt(candidate),
        existing=_fmt(existing_stub),
        match_type=match_type,
        matched_fields=", ".join(matched_fields or []),
    )

    try:
        resp = await llm.call(
            llm.FLASH,
            [{"role": "system", "content": _SYSTEM},
             {"role": "user",   "content": user_msg}],
            temperature=0.0,
            max_tokens=256,
        )
        response = resp.choices[0].message.content or ""
        raw = response.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        decision = json.loads(raw)
        return {
            **candidate,
            "review_decision": decision.get("decision", "needs_investigation"),
            "review_reason": decision.get("reason", ""),
        }
    except Exception as exc:
        log.warning("review_pair failed for %s: %s", candidate.get("name"), exc)
        return {
            **candidate,
            "review_decision": "needs_investigation",
            "review_reason": f"AI review error: {exc}",
        }


async def review_file(processed_path: Path) -> dict:
    """Review all needs_ai_review leads in a processed file.

    Writes a -reviewed.json file.  Returns summary stats.
    """
    data = json.loads(processed_path.read_text())
    flagged = data.get("needs_ai_review", [])

    if not flagged:
        log.info("no leads need AI review in %s", processed_path.name)
        return {"reviewed": 0, "same_org": 0, "different_orgs": 0, "needs_investigation": 0}

    log.info("reviewing %d flagged leads …", len(flagged))

    # Review all pairs concurrently (flash is fast)
    tasks = []
    for lead in flagged:
        rf = lead.get("review_flag") or lead.get("matched") or {}
        matched_name = (rf.get("matched_name") or
                        (lead.get("matched") or {}).get("matched_name") or
                        "unknown")
        match_type   = (rf.get("match_type") or
                        (lead.get("matched") or {}).get("match_type") or
                        "unknown")
        matched_fields = (rf.get("matched_fields") or
                          (lead.get("matched") or {}).get("matched_fields") or [])
        tasks.append(review_pair(lead, matched_name, match_type, matched_fields))

    reviewed = await asyncio.gather(*tasks)

    # Tally
    counts: dict[str, int] = {"same_org": 0, "different_orgs": 0, "needs_investigation": 0}
    for r in reviewed:
        counts[r.get("review_decision", "needs_investigation")] += 1

    # Write reviewed file
    out = {
        **data,
        "needs_ai_review": reviewed,   # same list, now annotated
        "review_summary": {
            "reviewed": len(reviewed),
            **counts,
        },
    }
    out_path = processed_path.with_name(
        processed_path.name.replace("-processed.json", "-reviewed.json")
    )
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    log.info("wrote %s", out_path)

    log.info("review summary: same_org=%d different_orgs=%d needs_investigation=%d",
             counts["same_org"], counts["different_orgs"], counts["needs_investigation"])
    return {"reviewed": len(reviewed), **counts, "output": str(out_path)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    if len(sys.argv) < 2:
        print("Usage: python -m app.pipeline.review <processed_file.json>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    result = await review_file(path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
