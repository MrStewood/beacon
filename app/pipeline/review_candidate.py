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
import subprocess
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

# Workflow states that are ready for review (or have no prior review decision)
_REVIEWABLE_STATES = {
    "yaml-created",
    "research-b-locked", "evidence-compared", "verified",
    "risk-verification-complete", "policy-checked", "trust-scored", "decision-signed",
}

# Workflow states that are already past review — skip re-review
_PAST_REVIEW_STATES = {
    "approved", "rejected", "needs_human_review",
    "pr-opened", "ci-passed", "merged",
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
                    "enum": ["approve", "reject", "needs_more_research", "needs_human_review"],
                    "description": (
                        "approve: publish as-is (or with minor corrections). "
                        "reject: not suitable for the directory. "
                        "needs_more_research: specific questions remain unanswered — pipeline will re-investigate. "
                        "needs_human_review: only for the two cases that genuinely require human judgment (see prompt)."
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
                    ],
                },

                # needs_human_review fields
                "human_reason": {
                    "type": "string",
                    "enum": [
                        "closing_existing_record",      # would mark an approved resource as closed
                        "public_access_unresolvable",   # two full passes, still unknown
                    ],
                    "description": "needs_human_review only: which of the two legitimate human-escalation triggers applies.",
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
  1. public_access is confirmed YES — this location serves individual members of the public
     (NOT a warehouse, distribution hub, or agency-only site)
  2. Phone/address confirmed in 2+ independent sources
  3. Currently operating — no closure evidence
  4. Category is accurate for the services provided at THIS location
  5. Not a known duplicate already in the directory
  Include `corrections` to fix any of these description quality issues:
  - Description exceeds 2 sentences → shorten to what the location actually does
  - Description contains program codes (TEFAP, CSFP, etc.) without plain-language explanation → rewrite in plain English
  - Description is about the org's statewide network, not this specific location → rewrite for this location
  - what_to_bring contains program descriptions instead of physical items → correct or remove
  - Hours are warehouse/office hours without confirmed public access → add caveat or move to access_notes

**reject** — if ANY of these are true:
  - public_access=no, or investigation evidence shows warehouse/distribution/agency-only
  - Eligibility text says "not listed as a public pantry" or "does not serve individuals"
  - Permanently closed (and NOT already an approved record — see needs_human_review)
  - Duplicate of an already-approved record
  - Not a genuine community resource (commercial, admin-only, etc.)
  NOTE: sensitive category (DV, crisis, children's) is NOT a reject reason.
  If the org's own website explicitly withholds an address, omit that field — that is handled.
  A crisis hotline with a confirmed public phone number should be APPROVED.

**needs_more_research** — if BOTH:
  - The resource is probably real and publicly accessible, BUT
  - Specific questions remain (hours unverified, eligibility unclear, phone unconfirmed)
  Provide concrete `guidance` and `questions_to_answer` for the next investigation pass.

**needs_human_review** — ONLY for these two cases, nothing else:
  1. The candidate would mark an *existing approved record* as permanently closed
     (`human_reason: closing_existing_record`)
  2. Two full investigation passes have been completed and public_access is STILL unknown
     (`human_reason: public_access_unresolvable`)
  Do NOT use this for sensitive categories, missing addresses, or any other reason.

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

    # --- Pre-flight gates (no LLM call needed) ---
    resource_pre = candidate.get("resource", {})
    public_access = str(resource_pre.get("public_access", "unknown")).lower().strip()
    county = (candidate_path.parent.name or "unknown").lower()

    if public_access == "no":
        reason = (
            "Auto-rejected: investigation found public_access=no — "
            "this location does not serve the general public directly "
            "(warehouse, distribution center, admin office, or agency-only site). "
            "If public access is actually available, re-investigate and record public_access=yes."
        )
        log.info("AUTO-REJECT %s — public_access=no", candidate_path.name)
        _do_reject(candidate, candidate_path, {
            "decision": "reject",
            "reasoning": reason,
            "confidence": "high",
        })
        return {"decision": "reject", "reasoning": reason, "auto": True}

    if public_access == "unknown":
        # If a requeue guidance file already exists this is the second attempt —
        # escalate to human rather than loop indefinitely.
        prior_requeue = candidate_path.with_suffix(".requeue.json").exists()
        if prior_requeue:
            log.info("NEEDS-HUMAN %s — public_access unknown after requeue", candidate_path.name)
            result = {
                "decision": "needs_human_review",
                "human_reason": "public_access_unresolvable",
                "reasoning": (
                    "Two investigation passes completed and public access is still unconfirmed. "
                    "A human must verify whether this location serves the general public."
                ),
                "confidence": "low",
            }
            _do_needs_human(candidate, candidate_path, result)
            return result
        log.info("AUTO-NEEDS-MORE-RESEARCH %s — public_access=unknown", candidate_path.name)
        result = {
            "decision": "needs_more_research",
            "reasoning": "Public access status was not confirmed during investigation.",
            "confidence": "low",
            "guidance": (
                "Confirm whether this location is open to the general public. "
                "Look for: walk-in hours, 'open to all', intake language on the org website. "
                "If it is a warehouse, distribution center, or serves agencies only, "
                "record public_access=no (will be auto-rejected). "
                "If it is publicly accessible, record public_access=yes."
            ),
            "questions_to_answer": [
                "Is this location open to the general public, or does it only serve partner agencies/organizations?",
                "Are the listed hours (if any) public walk-in hours or internal warehouse/office hours?",
            ],
        }
        _write_requeue(candidate, candidate_path, result)
        return result

    candidate_id = candidate.get("candidate_id", candidate_path.stem)
    resource     = candidate.get("resource", {})
    county       = (candidate_path.parent.name or "unknown").lower()  # set in pre-flight too; reuse same value
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
    elif decision == "needs_human_review":
        _do_needs_human(candidate, candidate_path, result)

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
    resource["last_verified"]       = _utc_now()[:10]
    resource["verified_by"]         = "review-agent"
    resource["confidence"]          = "medium"

    # workflow block — validate_sources.py reads workflow.verified_by
    resource["workflow"] = {
        "discovered_by": "lead-generation-agent",
        "verified_by":   "review-agent",
    }

    # sources block — validate_sources.py reads sources[].source_type
    existing_source_urls = resource.get("source_urls", [])
    resource["sources"] = [
        {"source_type": "official-provider", "url": u}
        for u in existing_source_urls[:3]
        if u
    ] or [{"source_type": "other", "url": resource.get("url", "")}]

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
    _git_commit_and_push(out_path, resource.get("name", "unknown"), county)

    # Remove from candidates
    candidate_path.unlink(missing_ok=True)
    requeue = candidate_path.with_suffix(".requeue.json")
    requeue.unlink(missing_ok=True)


def _git_commit_and_push(approved_path: Path, name: str, county: str) -> None:
    """Stage the approved YAML, commit, and push to origin main."""
    def _run(cmd: list[str]) -> tuple[int, str]:
        r = subprocess.run(cmd, cwd=BEACON_ROOT, capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr).strip()

    # Rebuild generated data files so the commit is self-consistent
    rc, out = _run([sys.executable, "scripts/build_from_yaml.py"])
    if rc != 0:
        log.warning("build_from_yaml failed (will still commit YAML): %s", out)

    # Stage the approved YAML and any regenerated data files
    rel = str(approved_path.relative_to(BEACON_ROOT))
    _run(["git", "add", rel,
          "data/resources.json", "data/resources.csv",
          "data/index.json", "data/catalog.json",
          "data/v3/resources.json"])

    msg = f"feat(resource): add {name} [{county}] [auto-approved]"
    rc, out = _run(["git", "commit", "-m", msg,
                    "--author=Beacon Review Agent <beacon-agent@mrstewood.github.io>"])
    if rc != 0:
        log.warning("git commit failed: %s", out)
        return
    log.info("git commit: %s", msg)

    rc, out = _run(["git", "push", "origin", "main"])
    if rc != 0:
        log.error("git push failed: %s", out)
    else:
        log.info("git push OK → CI will deploy")


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


def _do_needs_human(candidate: dict, candidate_path: Path, review: dict) -> None:
    """Move candidate to needs-human-review queue."""
    HUMAN_DIR = BEACON_ROOT / "leads" / "needs_human_review"
    HUMAN_DIR.mkdir(parents=True, exist_ok=True)
    dest = HUMAN_DIR / candidate_path.name
    dest.write_text(candidate_path.read_text())
    candidate_path.unlink()
    reason = review.get("human_reason", "unspecified")
    log.info("NEEDS HUMAN REVIEW → %s (reason: %s)", dest.name, reason)
    log.info("  Reasoning: %s", review.get("reasoning", ""))


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
