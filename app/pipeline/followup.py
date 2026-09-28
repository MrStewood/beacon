"""
Follow-up Investigation
=======================
Answers the specific questions from a reviewer's needs_more_research decision,
then rebuilds the candidate YAML and re-runs the review.

Usage
-----
    python -m app.pipeline.followup source/candidates/laurel/<id>.requeue.json
    python -m app.pipeline.followup --all   # process all pending requeues

Flow
----
    <id>.requeue.json  →  targeted agent (answers questions, records new findings)
                       →  merged investigation JSON
                       →  rebuilt candidate YAML (with new evidence)
                       →  re-review
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app import agent
from app.tools import BrowserSession, SearchSession, session_tools
from app.tools.wayback import WAYBACK_CHECK_SCHEMA, handle_wayback_check

log = logging.getLogger(__name__)

BEACON_ROOT    = Path(__file__).resolve().parents[2]
CANDIDATES_DIR = BEACON_ROOT / "source" / "candidates"


# ---------------------------------------------------------------------------
# answer_question tool — agent records explicit answers to reviewer questions
# ---------------------------------------------------------------------------

ANSWER_QUESTION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "answer_question",
        "description": (
            "Record a direct answer to one of the reviewer's specific questions. "
            "Call once per question. Be direct — yes/no + one sentence of evidence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The exact question from the reviewer (copy it verbatim).",
                },
                "answer": {
                    "type": "string",
                    "description": "Direct answer. Start with YES or NO if applicable, then one sentence of evidence.",
                },
                "evidence_url": {
                    "type": "string",
                    "description": "URL where you found the answer.",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                },
                "content_hash": {
                    "type": "string",
                    "description": "SHA-256 from the navigate response for this page.",
                },
            },
            "required": ["question", "answer", "confidence"],
        },
    },
}

# Reuse record_finding and complete_pass from investigate.py
from app.pipeline.investigate import (
    RECORD_FINDING_SCHEMA,
    COMPLETE_PASS_SCHEMA,
    InvestigationStore,
    _lead_id,
    INVESTIGATIONS_DIR,
)


# ---------------------------------------------------------------------------
# Follow-up store — wraps InvestigationStore, adds answer_question
# ---------------------------------------------------------------------------

class FollowUpStore:
    def __init__(self, lead: dict, prior_findings: list[dict]):
        self._inv_store = InvestigationStore(lead)
        # Seed with prior findings so ev_counter doesn't collide
        self._inv_store.findings = list(prior_findings)
        self._inv_store._ev_counter = len(prior_findings)
        self.answers: list[dict] = []

    async def handle_answer_question(self, args: dict) -> str:
        entry = {
            "question":    args.get("question", ""),
            "answer":      args.get("answer", ""),
            "evidence_url": args.get("evidence_url", ""),
            "confidence":  args.get("confidence", "medium"),
            "content_hash": args.get("content_hash"),
            "answered_at": _utc_now(),
        }
        self.answers.append(entry)
        log.info("answered: %s… → %s", args.get("question","")[:60], args.get("answer","")[:80])
        return json.dumps({"recorded": True, "question": args.get("question", "")[:60]})

    def tool_schemas(self) -> list[dict]:
        return [
            ANSWER_QUESTION_SCHEMA,
            RECORD_FINDING_SCHEMA,
            COMPLETE_PASS_SCHEMA,
            WAYBACK_CHECK_SCHEMA,
        ]

    def tool_handlers(self) -> dict:
        return {
            "answer_question": self.handle_answer_question,
            "record_finding":  self._inv_store.handle_record_finding,
            "complete_pass":   self._inv_store.handle_complete_pass,
            "wayback_check":   handle_wayback_check,
        }

    @property
    def new_findings(self) -> list[dict]:
        return self._inv_store.findings[len(self._inv_store.findings) -
                                        (self._inv_store._ev_counter - len(self._inv_store.findings)):]

    def all_findings(self) -> list[dict]:
        return self._inv_store.findings

    def pass_completion(self) -> dict:
        return self._inv_store.pass_completions.get("C", {})


# ---------------------------------------------------------------------------
# System prompt for follow-up pass
# ---------------------------------------------------------------------------

def _followup_prompt(
    lead: dict,
    requeue: dict,
    prior_findings: list[dict],
    candidate: dict,
) -> str:
    name     = lead.get("name", "")
    city     = lead.get("city", "") or ""
    state    = lead.get("state", "") or ""
    area     = f"{city}, {state}".strip(", ")

    questions_block = "\n".join(
        f"  {i+1}. {q}" for i, q in enumerate(requeue.get("questions_to_answer", []))
    ) or "  (no specific questions — see guidance)"

    missing_block = ", ".join(requeue.get("missing_fields", [])) or "none"

    # What we already know — brief summary from prior findings
    known: dict[str, str] = {}
    for f in prior_findings:
        if f["field"] not in known and not f.get("conflicts_with"):
            known[f["field"]] = str(f["value"])[:60]
    known_block = "\n".join(f"  {k}: {v}" for k, v in known.items()) or "  (nothing)"

    guidance = requeue.get("guidance", "")
    reasoning = requeue.get("reviewer_reasoning", "")

    return f"""You are a targeted follow-up investigator for Beacon community resource directory.

A human-quality AI reviewer examined the candidate for '{name}' and sent it back
because specific questions need answers before it can be published.

## Reviewer's reasoning
{reasoning}

## Questions you MUST answer
{questions_block}

## Missing fields to find (if possible)
{missing_block}

## Reviewer's specific guidance on where to look
{guidance}

## What we already know (do not repeat this research)
{known_block}

## Your job — PASS C (Targeted Follow-up)

1. Follow the reviewer's guidance above — those are specific instructions on where to look.
2. For EACH question: search/navigate to find the answer, then call answer_question().
3. If you find any new field values: call record_finding(pass='C', ...) with content_hash.
4. Call screenshot(label='...') on every page you extract facts from.
5. Call complete_pass(pass='C', ...) when done — list any questions you could NOT answer.

## Available tools (use ONLY these)
  - navigate(url)          — load page; response includes [content_hash: sha256:...]
  - search(query)          — web search
  - get_links()            — list links on current page
  - scroll_down()          — scroll current page
  - screenshot(label)      — save screenshot as evidence
  - answer_question(...)   — record a direct answer to a reviewer question ← PRIMARY TOOL
  - record_finding(...)    — record a new field value with evidence
  - complete_pass(...)     — finish this pass (REQUIRED — call when done)
  - wayback_check(url)     — check for existing Wayback snapshot

## Rules
  - Answer every question. If you cannot find the answer after 2 searches, answer with
    confidence='low' and explain what you tried.
  - NEVER invent. If genuinely unknown: say "Could not confirm after searching X and Y."
  - Budget: ~10 steps. Answer questions first, then record any bonus new findings.
  - complete_pass(pass='C') is REQUIRED to end.
""".strip()


# ---------------------------------------------------------------------------
# Main follow-up runner
# ---------------------------------------------------------------------------

async def run_followup(requeue_path: Path) -> dict:
    """Run a targeted follow-up investigation for a requeued candidate."""

    requeue = json.loads(requeue_path.read_text())
    candidate_id = requeue.get("candidate_id", requeue_path.stem.replace(".requeue", ""))

    # Find the candidate YAML
    candidate_path = None
    for p in CANDIDATES_DIR.rglob(f"{candidate_id}.yaml"):
        candidate_path = p
        break
    if not candidate_path or not candidate_path.exists():
        raise FileNotFoundError(f"Candidate YAML not found for {candidate_id}")

    candidate = yaml.safe_load(candidate_path.read_text())
    resource  = candidate.get("resource", {})

    # Reconstruct the lead from the candidate resource
    locations = resource.get("locations", [{}])
    loc       = locations[0] if locations else {}
    addr      = loc.get("address", {})
    lead = {
        "name":    resource.get("name", ""),
        "category": (resource.get("needs") or ["community"])[0],
        "city":    addr.get("city", ""),
        "state":   addr.get("state", ""),
        "zip":     addr.get("zip", ""),
        "county":  addr.get("county", ""),
        "url":     resource.get("url", ""),
        "phone":   (loc.get("phones") or [""])[0],
    }

    # Load prior investigation findings
    zip_   = addr.get("zip", "")
    prior_findings: list[dict] = []
    inv_path: Path | None = None

    if zip_:
        inv_dir = INVESTIGATIONS_DIR / zip_
        if inv_dir.exists():
            matches = sorted(inv_dir.glob(f"{zip_}-*.json"), key=lambda p: p.stat().st_mtime)
            if matches:
                inv_path = matches[-1]
                inv_data  = json.loads(inv_path.read_text())
                prior_findings = inv_data.get("findings", [])
                log.info("loaded %d prior findings from %s", len(prior_findings), inv_path.name)

    log.info("=== follow-up: %s (%d questions) ===",
             lead["name"], len(requeue.get("questions_to_answer", [])))

    store = FollowUpStore(lead, prior_findings)

    evidence_dir = INVESTIGATIONS_DIR / zip_ / f"{_lead_id(lead)}-followup-evidence"

    async with BrowserSession(evidence_dir=evidence_dir) as browser:
        async with SearchSession() as search:
            br_schemas, br_handlers = session_tools(browser, search)

            all_schemas  = br_schemas + store.tool_schemas()
            all_handlers = {**br_handlers, **store.tool_handlers()}

            system = _followup_prompt(lead, requeue, prior_findings, candidate)
            user   = (
                f"Answer the reviewer's questions about '{lead['name']}' in {lead.get('city','')}, "
                f"{lead.get('state','')}. Run Pass C now."
            )

            await agent.run(
                system=system,
                user=user,
                tools=all_schemas,
                extra_handlers=all_handlers,
                max_steps=40,
            )

    # Build updated investigation
    pass_c = store.pass_completion()
    all_findings = store.all_findings()

    # Load the prior full investigation to merge into
    if inv_path:
        merged_inv = json.loads(inv_path.read_text())
    else:
        merged_inv = {
            "lead_id":         _lead_id(lead),
            "investigated_at": _utc_now(),
            "lead":            lead,
            "findings":        prior_findings,
            "pass_a":          {},
            "pass_b":          {},
            "summary":         {},
        }

    # Add Pass C findings and answers
    new_findings = [f for f in all_findings if f.get("pass") == "C"]
    merged_inv["findings"] = [f for f in all_findings]  # includes prior + new
    merged_inv["pass_c"] = {
        **pass_c,
        "answers": store.answers,
    }
    merged_inv["summary"] = {
        "total_findings": len(merged_inv["findings"]),
        "pass_a_count":   len([f for f in merged_inv["findings"] if f.get("pass") == "A"]),
        "pass_b_count":   len([f for f in merged_inv["findings"] if f.get("pass") == "B"]),
        "pass_c_count":   len(new_findings),
        "fields_found":   sorted({f["field"] for f in merged_inv["findings"]}),
        "answers":        store.answers,
        "conflicts":      [f for f in merged_inv["findings"] if f.get("conflicts_with")],
        "operating_status": (
            pass_c.get("operating_status") or
            merged_inv.get("pass_b", {}).get("operating_status") or
            merged_inv.get("pass_a", {}).get("operating_status") or
            "unclear"
        ),
        "risk_tier": (
            pass_c.get("proposed_risk_tier") or
            merged_inv.get("pass_b", {}).get("proposed_risk_tier") or
            "low"
        ),
    }

    # Save updated investigation (overwrite)
    if inv_path:
        out_path = inv_path
    else:
        out_dir  = INVESTIGATIONS_DIR / (zip_ or "unknown")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{_lead_id(lead)}.json"

    out_path.write_text(json.dumps(merged_inv, indent=2, ensure_ascii=False))
    log.info("updated investigation → %s", out_path.relative_to(BEACON_ROOT))

    # Rebuild candidate YAML with new evidence
    log.info("rebuilding candidate YAML …")
    from app.pipeline.candidate import build_candidate
    new_candidate_path = build_candidate(out_path)
    log.info("rebuilt → %s", new_candidate_path.relative_to(BEACON_ROOT))

    # Remove the requeue file — it's been actioned
    requeue_path.unlink()
    log.info("removed requeue file")

    # Re-run the review
    log.info("re-running review …")
    from app.pipeline.review_candidate import review_candidate
    review_result = await review_candidate(new_candidate_path)

    return {
        "candidate_id":   candidate_id,
        "new_findings":   len(new_findings),
        "questions_asked": len(requeue.get("questions_to_answer", [])),
        "questions_answered": len(store.answers),
        "answers": store.answers,
        "review_decision": review_result.get("decision"),
        "review_confidence": review_result.get("confidence"),
        "review_reasoning":  review_result.get("reasoning"),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    g.add_argument("requeue", nargs="?", help="Path to .requeue.json file")
    g.add_argument("--all", action="store_true", help="Process all pending requeue files")
    args = p.parse_args()

    if args.all:
        files = sorted(CANDIDATES_DIR.rglob("*.requeue.json"))
        log.info("processing %d requeue files", len(files))
        for f in files:
            try:
                result = await run_followup(f)
                print(f"{f.name}: {result['review_decision']} "
                      f"({result['questions_answered']}/{result['questions_asked']} answered)")
            except Exception as exc:
                log.error("%s failed: %s", f.name, exc)
    else:
        path = Path(args.requeue)
        if not path.exists():
            print(f"Not found: {path}", file=sys.stderr)
            sys.exit(1)
        result = await run_followup(path)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
