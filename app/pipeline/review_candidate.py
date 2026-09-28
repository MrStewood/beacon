"""
AI Candidate Reviewer
=====================
Reviews a candidate YAML and makes one of three decisions:

  approve            → writes to source/approved/<county>/<id>.yaml
  reject             → moves to leads/rejected/<id>.yaml with reason
  needs_more_research → writes guidance file, marks candidate for re-investigation

The reviewer has access to browser + search for targeted clarification (2–3 queries max).
It does NOT re-investigate — it resolves specific open questions.

Usage
-----
    python -m app.pipeline.review_candidate source/candidates/laurel/<id>.yaml
    python -m app.pipeline.review_candidate --all   # review all pending candidates
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app import agent
from app.tools import BrowserSession, SearchSession, session_tools

log = logging.getLogger(__name__)

BEACON_ROOT    = Path(__file__).resolve().parents[2]
APPROVED_DIR   = BEACON_ROOT / "source" / "approved"
CANDIDATES_DIR = BEACON_ROOT / "source" / "candidates"
REJECTED_DIR   = BEACON_ROOT / "leads" / "rejected"
REVIEWS_DIR    = BEACON_ROOT / "leads" / "reviews"

# Workflow states that mean "ready for review"
_REVIEWABLE_STATES = {
    "research-b-locked", "evidence-compared", "verified",
    "risk-verification-complete", "policy-checked", "trust-scored", "decision-signed",
}

# Workflow states that are already past review
_PAST_REVIEW_STATES = {
    "yaml-created", "pr-opened", "ci-passed", "merged",
    "deployed", "production-verified", "monitoring",
}


# ---------------------------------------------------------------------------
# complete_review tool
# ---------------------------------------------------------------------------

COMPLETE_REVIEW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "complete_review",
        "description": (
            "Submit your review decision. Call this exactly once when you are ready. "
            "This is the only way to end the review — you MUST call it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["approve", "reject", "needs_more_research"],
                    "description": (
                        "approve: publish as-is (or with minor corrections). "
                        "reject: not suitable for the directory. "
                        "needs_more_research: specific questions remain unanswered."
                    ),
                },
                "reasoning": {
                    "type": "string",
                    "description": "1–3 sentences explaining the decision. Be specific.",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "How confident are you in this decision?",
                },

                # approve fields
                "corrections": {
                    "type": "object",
                    "description": (
                        "approve only: any field corrections to apply before publishing. "
                        "e.g. {\"hours\": \"Mon-Fri 9am-5pm\", \"description\": \"updated text\"}"
                    ),
                },

                # reject fields
                "reject_reason": {
                    "type": "string",
                    "enum": [
                        "not_public_facing",    # agency-only, warehouse, admin office
                        "permanently_closed",
                        "duplicate",
                        "out_of_scope",         # commercial, not a community resource
                        "insufficient_evidence",# can't confirm it's real
                        "sensitive_requires_manual", # DV shelter location, crisis
                    ],
                },

                # needs_more_research fields
                "questions_to_answer": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "needs_more_research only: specific yes/no or fact questions "
                        "the next investigation pass must answer. Be concrete."
                    ),
                },
                "guidance": {
                    "type": "string",
                    "description": (
                        "needs_more_research only: specific instructions for the "
                        "next investigation pass. Where to look, what to search for."
                    ),
                },
                "missing_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "needs_more_research only: field names that must be found.",
                },
            },
            "required": ["decision", "reasoning", "confidence"],
        },
    },
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _review_prompt(candidate: dict, investigation: dict | None) -> str:
    resource   = candidate.get("resource", {})
    decision   = candidate.get("decision", {})
    claims     = candidate.get("claims", [])
    rps        = candidate.get("research_packages", [])
    risk_tier  = candidate.get("risk_tier", "low")
    score      = decision.get("record_trust_score", "?")
    lowest     = decision.get("lowest_essential_claim_score", "?")
    outcome    = decision.get("outcome", "?")

    name       = resource.get("name", "?")
    category   = (resource.get("needs") or ["?"])[0]
    locations  = resource.get("locations", [])
    loc        = locations[0] if locations else {}
    addr_obj   = loc.get("address", {})
    address    = f"{addr_obj.get('street','')}, {addr_obj.get('city','')}, {addr_obj.get('state','')}".strip(", ")
    phones     = loc.get("phones", [])
    hours      = loc.get("hours", "unknown")
    url        = resource.get("url", "")
    eligibility = resource.get("eligibility", "")
    description = resource.get("description", "")

    # Essential claim summary
    essential_lines = []
    for cl in claims:
        if cl.get("essential"):
            essential_lines.append(
                f"  {cl['field']:<20} score={cl.get('score','?'):<4} "
                f"status={cl.get('status','?')}"
            )

    # Researcher concerns
    concerns = []
    for rp in rps:
        for d in rp.get("possible_duplicates", []):
            concerns.append(f"Possible duplicate: {d}")
        for u in rp.get("unknown_fields", []):
            concerns.append(f"Unknown field: {u}")
        for lim in rp.get("limitations", []):
            if lim.strip():
                concerns.append(f"Limitation: {lim}")

    concerns_block = "\n".join(f"  - {c[:120]}" for c in concerns[:12]) or "  (none)"

    # Investigation summary if available
    inv_summary = ""
    if investigation:
        s = investigation.get("summary", {})
        inv_summary = (
            f"\n## Investigation summary\n"
            f"  Findings: {s.get('total_findings',0)} "
            f"(Pass A: {s.get('pass_a_count',0)}, Pass B: {s.get('pass_b_count',0)})\n"
            f"  Fields found: {', '.join(s.get('fields_found', []))}\n"
            f"  Conflicts: {len(s.get('conflicts', []))}"
        )

    return f"""You are the Beacon Resource Quality Reviewer.
Beacon is a community resource directory that helps people in need find food, shelter, healthcare, legal aid, and 17 other categories of help.

## Candidate to review

Name:       {name}
Category:   {category}
Address:    {address}
Phone(s):   {', '.join(phones) if phones else 'none found'}
Hours:      {hours}
URL:        {url}
Eligibility:{eligibility}
Description:{description[:200]}

## Trust scores
  Record trust score:    {score}/100  (threshold: 80)
  Lowest essential:      {lowest}/100  (threshold: 75)
  Scoring outcome:       {outcome}
  Risk tier:             {risk_tier}

## Essential claim scores
{chr(10).join(essential_lines) or '  (none)'}

## Researcher concerns
{concerns_block}
{inv_summary}

## Your job

Review this candidate and call complete_review() with ONE decision:

**approve** — if ALL of these are true:
  1. Real organization that serves the general public (not agencies-only, not a warehouse)
  2. Phone/address confirmed in 2+ independent sources (check claim scores above)
  3. Currently operating — no evidence of closure
  4. Category is accurate
  5. Not a known duplicate already in the directory
  You may include minor `corrections` (e.g. cleaner hours format, better description).

**reject** — if ANY of these are true:
  - Not public-facing (warehouse distributes to agencies, not individuals)
  - Permanently closed
  - Duplicate of an already-approved record
  - Not a genuine community resource (commercial, admin-only, etc.)
  - Sensitive resource requiring manual review (DV shelter location)

**needs_more_research** — if BOTH:
  - The resource is probably real and public-facing, BUT
  - Specific answerable questions remain (hours, eligibility, public vs agency access)
  Provide concrete `guidance` and `questions_to_answer` for the next investigation pass.

## Tools available (use sparingly — 2–3 searches max)
  - search(query) — for targeted clarification only
  - navigate(url) — visit a specific page to resolve a question

Do your research, then call complete_review(). That is the only way to end.
""".strip()


# ---------------------------------------------------------------------------
# Review runner
# ---------------------------------------------------------------------------

async def review_candidate(candidate_path: Path) -> dict:
    """Run AI review on a candidate YAML. Returns decision dict."""
    candidate = yaml.safe_load(candidate_path.read_text())

    state = candidate.get("workflow_state", "")
    if state in _PAST_REVIEW_STATES:
        log.info("skipping %s — already past review (%s)", candidate_path.name, state)
        return {"decision": "already_processed", "workflow_state": state}

    candidate_id = candidate.get("candidate_id", candidate_path.stem)
    resource     = candidate.get("resource", {})
    county       = (candidate_path.parent.name or "unknown").lower()
    zip_         = (resource.get("locations") or [{}])[0].get("address", {}).get("zip", "")

    # Load matching investigation if it exists
    investigation = None
    inv_dir = BEACON_ROOT / "leads" / "investigations" / zip_
    if zip_ and inv_dir.exists():
        matches = list(inv_dir.glob(f"{zip_}-*.json"))
        if matches:
            # Best match: slug overlap
            name_slug = re.sub(r"[^a-z0-9]+", "-",
                               resource.get("name", "").lower()).strip("-")
            best = max(matches, key=lambda p: _slug_overlap(p.stem, name_slug))
            try:
                investigation = json.loads(best.read_text())
            except Exception:
                pass

    decision_holder: dict[str, Any] = {}

    async def handle_complete_review(args: dict) -> str:
        decision_holder.update(args)
        log.info("review decision: %s (confidence=%s)", args.get("decision"), args.get("confidence"))
        return json.dumps({"recorded": True, "decision": args.get("decision")})

    system = _review_prompt(candidate, investigation)
    user   = f"Review '{resource.get('name', candidate_id)}' and call complete_review()."

    async with BrowserSession(evidence_dir=REVIEWS_DIR / "browser-evidence") as browser:
        async with SearchSession() as search:
            schemas, handlers = session_tools(browser, search)
            schemas  = schemas + [COMPLETE_REVIEW_SCHEMA]
            handlers["complete_review"] = handle_complete_review

            await agent.run(
                system=system,
                user=user,
                tools=schemas,
                extra_handlers=handlers,
                max_steps=30,
            )

    if not decision_holder:
        log.warning("reviewer did not call complete_review — defaulting to needs_more_research")
        decision_holder = {
            "decision": "needs_more_research",
            "reasoning": "Reviewer did not produce a decision.",
            "confidence": "low",
            "guidance": "Re-run review.",
        }

    decision = decision_holder.get("decision")
    result   = {
        "candidate_id":  candidate_id,
        "reviewed_at":   _utc_now(),
        "candidate_path": str(candidate_path.resolve().relative_to(BEACON_ROOT)),
        **decision_holder,
    }

    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    review_path = REVIEWS_DIR / f"{candidate_id}-review.json"
    review_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    log.info("review saved → %s", review_path.relative_to(BEACON_ROOT))

    # Act on the decision
    if decision == "approve":
        _do_approve(candidate, candidate_path, county, result)
    elif decision == "reject":
        _do_reject(candidate, candidate_path, result)
    elif decision == "needs_more_research":
        _do_requeue(candidate, candidate_path, result)

    return result


# ---------------------------------------------------------------------------
# Decision actions
# ---------------------------------------------------------------------------

def _do_approve(candidate: dict, candidate_path: Path, county: str, review: dict) -> None:
    """Write approved resource YAML to source/approved/<county>/<id>.yaml."""
    resource = dict(candidate.get("resource", {}))

    # Apply any corrections the reviewer specified
    corrections = review.get("corrections") or {}
    if corrections:
        log.info("applying %d corrections from reviewer", len(corrections))
        _apply_corrections(resource, corrections)

    # Stamp verification info
    resource["verification_status"] = "verified"
    resource["verified_at"]         = _utc_now()
    resource["verified_by"]         = "review-agent"

    out_dir = APPROVED_DIR / county
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{candidate.get('candidate_id', 'unknown')}.yaml"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Approved resource — {resource.get('name', '')}\n")
        f.write(f"# Reviewed: {_utc_now()}\n")
        f.write(f"# Reviewer decision: {review.get('reasoning', '')}\n\n")
        yaml.dump(resource, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, width=120)

    log.info("APPROVED → %s", out_path.relative_to(BEACON_ROOT))

    # Update candidate workflow_state
    candidate["workflow_state"] = "yaml-created"
    candidate["audit"] = candidate.get("audit", []) + [{
        "state": "yaml-created",
        "actor": "review-agent",
        "actor_role": "publisher",
        "at": _utc_now(),
        "note": review.get("reasoning", ""),
    }]
    candidate_path.write_text(
        yaml.dump(candidate, allow_unicode=True, sort_keys=False, width=120)
    )


def _do_reject(candidate: dict, candidate_path: Path, review: dict) -> None:
    """Move candidate to rejected queue."""
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    reject_path = REJECTED_DIR / candidate_path.name
    reject_data = {
        **candidate,
        "workflow_state": "rejected",
        "rejection": {
            "reason":     review.get("reject_reason", "unspecified"),
            "reasoning":  review.get("reasoning", ""),
            "reviewed_at": _utc_now(),
            "reviewer":   "review-agent",
        },
    }
    reject_path.write_text(
        yaml.dump(reject_data, allow_unicode=True, sort_keys=False, width=120)
    )
    # Remove from candidates
    candidate_path.unlink()
    log.info("REJECTED → %s (reason: %s)", reject_path.name, review.get("reject_reason"))


def _do_requeue(candidate: dict, candidate_path: Path, review: dict) -> None:
    """Write guidance file so next investigation pass knows what to find."""
    guidance_path = candidate_path.with_suffix(".requeue.json")
    guidance_path.write_text(json.dumps({
        "candidate_id":      candidate.get("candidate_id"),
        "requeue_at":        _utc_now(),
        "reviewer_reasoning": review.get("reasoning", ""),
        "guidance":          review.get("guidance", ""),
        "questions_to_answer": review.get("questions_to_answer", []),
        "missing_fields":    review.get("missing_fields", []),
    }, indent=2, ensure_ascii=False))
    log.info("NEEDS MORE RESEARCH → guidance written to %s", guidance_path.name)
    log.info("  Questions: %s", review.get("questions_to_answer", []))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_corrections(resource: dict, corrections: dict) -> None:
    """Apply reviewer field corrections to the resource dict."""
    for field, value in corrections.items():
        if "." in field:
            # nested: e.g. "locations.0.hours"
            parts = field.split(".")
            obj = resource
            for part in parts[:-1]:
                if part.isdigit():
                    obj = obj[int(part)]
                else:
                    obj = obj.setdefault(part, {})
            last = parts[-1]
            if last.isdigit():
                obj[int(last)] = value
            else:
                obj[last] = value
        else:
            resource[field] = value


def _slug_overlap(a: str, b: str) -> int:
    a_words = set(a.split("-"))
    b_words = set(b.split("-"))
    return len(a_words & b_words)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    import argparse
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("candidate", nargs="?", help="Path to candidate YAML")
    g.add_argument("--all", action="store_true", help="Review all pending candidates")
    args = p.parse_args()

    if args.all:
        paths = sorted(CANDIDATES_DIR.rglob("*.yaml"))
        paths = [p for p in paths if p.name != "README.md"]
        log.info("reviewing %d candidates", len(paths))
        for path in paths:
            result = await review_candidate(path)
            print(f"{path.name}: {result.get('decision')} ({result.get('confidence','?')})")
    else:
        path = Path(args.candidate)
        if not path.exists():
            print(f"Not found: {path}", file=sys.stderr)
            sys.exit(1)
        result = await review_candidate(path)
        print(json.dumps({
            "decision":   result.get("decision"),
            "confidence": result.get("confidence"),
            "reasoning":  result.get("reasoning"),
            "questions":  result.get("questions_to_answer"),
            "guidance":   result.get("guidance"),
            "corrections":result.get("corrections"),
        }, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
