"""
Lead Investigation Agent
========================
Two-pass agent that verifies and enriches a raw lead into a structured
investigation result ready for candidate YAML generation.

Pass A — Primary source research
  Navigate org's own website; extract every field; archive pages in Wayback.

Pass B — Independent corroboration
  Find 2+ independent sources (211, county directory, state DB, news);
  confirm or contradict Pass A findings; archive corroborating pages.

Both passes run the same agent loop with different instructions. The agent
uses record_finding() to log each piece of evidence as it goes, and
complete_pass() to lock the research package.

Usage
-----
    python -m app.pipeline.investigate <lead_key>
    python -m app.pipeline.investigate --file leads/runs/40744/run-raw.json --name "God's Pantry"
    python -m app.pipeline.investigate --json '{"name": "...", "category": "food", ...}'
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sys
import textwrap
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app import agent, llm
from app.tools import BrowserSession, SearchSession, session_tools
from app.tools.wayback import WAYBACK_CHECK_SCHEMA, handle_wayback_check

log = logging.getLogger(__name__)

BEACON_ROOT = Path(__file__).resolve().parents[2]
INVESTIGATIONS_DIR = BEACON_ROOT / "leads" / "investigations"


# ---------------------------------------------------------------------------
# Category-specific field guidance
# ---------------------------------------------------------------------------

_CATEGORY_FIELDS: dict[str, dict] = {
    "food": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["hours", "eligibility", "what_to_bring", "description", "service_area"],
        "guidance":  "Hours and distribution schedule are critical. Is this location open to the GENERAL PUBLIC (not a warehouse, distribution center, or agency-only site)? Record public_access=yes/no/unknown. Note whether walk-in or appointment. Find out what kinds of food are distributed (box, choice pantry, hot meal). what_to_bring: ONLY physical items to bring (ID, proof of address, proof of income) — not program descriptions.",
    },
    "shelter": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["hours", "eligibility", "capacity", "intake_process", "populations", "service_area"],
        "guidance":  "Who is served (men/women/families/anyone)? Is sobriety required? What is the intake process? Is there a waitlist? What is the nightly or stay limit?",
    },
    "housing": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["eligibility", "intake_process", "description", "service_area"],
        "guidance":  "Is there a waitlist? Income limits? Application process? Section 8 vs transitional vs permanent supportive?",
    },
    "health": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["hours", "eligibility", "cost", "intake_process", "description", "service_area"],
        "guidance":  "What insurance is accepted? Is there a sliding fee scale? Appointment vs walk-in? What services are offered (primary care, dental, vision, Rx)?",
    },
    "mental-health": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["hours", "eligibility", "cost", "intake_process", "service_area"],
        "guidance":  "Medicaid/Medicare accepted? Sliding scale? Crisis line available 24/7? Specific populations served (youth, adults, veterans)?",
    },
    "addiction": {
        "essential": ["phone", "operating_status"],
        "material":  ["address", "eligibility", "cost", "intake_process", "populations", "description", "service_area"],
        "guidance":  "Level of care: detox, residential, outpatient, MAT? Gender-specific? Insurance/Medicaid accepted? Walk-in or referral required?",
    },
    "crisis": {
        "essential": ["phone", "operating_status"],
        "material":  ["hours", "eligibility", "populations", "intake_process", "service_area"],
        "guidance":  "Is this a hotline (phone only) or physical location? 24/7? If physical location: is address confidential (DV shelter)? Do NOT publish a confidential shelter address.",
        "sensitive": True,
    },
    "family": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["eligibility", "hours", "populations", "description", "service_area"],
        "guidance":  "Age ranges for children served? Income limits? Appointment or walk-in? Head Start vs Early Head Start vs childcare?",
    },
    "legal": {
        "essential": ["phone", "public_access", "operating_status"],
        "material":  ["address", "hours", "eligibility", "intake_process", "description", "service_area"],
        "guidance":  "Income eligibility? Case types accepted (family, housing, benefits, criminal)? Walk-in clinics or appointment only?",
    },
    "documents": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["hours", "eligibility", "cost", "description", "service_area"],
        "guidance":  "What documents can be obtained? Fee assistance available? Walk-in or appointment?",
    },
    "education": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["hours", "eligibility", "cost", "description", "service_area"],
        "guidance":  "GED, ESL, literacy, vocational? Cost or free? Online or in-person?",
    },
    "jobs": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["hours", "eligibility", "description", "service_area"],
        "guidance":  "Resume help, job placement, training programs? What industries? Income eligibility?",
    },
    "transportation": {
        "essential": ["phone", "operating_status"],
        "material":  ["hours", "eligibility", "cost", "description", "service_area"],
        "guidance":  "Medical transport vs general? Medicaid-funded? Appointment required? Service area?",
    },
    "utility-assistance": {
        "essential": ["phone", "operating_status"],
        "material":  ["address", "hours", "eligibility", "description", "service_area"],
        "guidance":  "LIHEAP, ECIP, or local fund? Income limits? Season or year-round? Electric, gas, water?",
    },
    "clothing": {
        "essential": ["phone", "public_access", "address", "operating_status"],
        "material":  ["hours", "eligibility", "description", "service_area"],
        "guidance":  "Free or voucher? Walk-in or appointment? What items available?",
    },
    "community": {
        "essential": ["phone", "operating_status"],
        "material":  ["address", "hours", "description", "service_area"],
        "guidance":  "What specific services does this organization provide?",
    },
    "veterans": {
        "essential": ["phone", "public_access", "operating_status"],
        "material":  ["address", "hours", "eligibility", "description", "service_area"],
        "guidance":  "Which branch/era? VSO vs VA? Benefits counseling, employment, housing, healthcare? Walk-in or appointment?",
    },
}

# Source type → tier mapping for candidate.py scoring
SOURCE_TIER: dict[str, str] = {
    "org-website":          "A",
    "gov-directory":        "B",
    "state-database":       "B",
    "established-directory":"C",   # 211, United Way, Feeding America
    "local-news":           "D",
    "social-media":         "E",
    "other":                "E",
}

# Source type → directness
SOURCE_DIRECTNESS: dict[str, int] = {
    "org-website":          20,
    "gov-directory":        15,
    "state-database":       15,
    "established-directory":15,
    "local-news":            8,
    "social-media":          8,
    "other":                 0,
}


# ---------------------------------------------------------------------------
# record_finding tool
# ---------------------------------------------------------------------------

RECORD_FINDING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "record_finding",
        "description": (
            "Record a verified fact about this organization with its source evidence. "
            "Call once per field per source. If a second source confirms the same value, "
            "call again with pass='B' and the same field — this builds corroboration. "
            "If a second source gives a DIFFERENT value, call with the new value and "
            "set conflicts_with to describe what it contradicts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pass": {
                    "type": "string",
                    "enum": ["A", "B"],
                    "description": "A = primary source (org's own website/official record). B = corroborating source (directory, news, 211).",
                },
                "field": {
                    "type": "string",
                    "description": "Field: phone|address|hours|eligibility|what_to_bring|cost|operating_status|description|url|email|facebook|intake_process|populations|service_types|languages|capacity|coverage_scope|service_area|public_access|access_notes",
                },
                "value": {
                    "description": "The actual value found. Exact quote or structured value — never paraphrase phone numbers or addresses.",
                },
                "source_url": {
                    "type": "string",
                    "description": "Exact URL where you found this value.",
                },
                "source_type": {
                    "type": "string",
                    "enum": ["org-website", "gov-directory", "state-database",
                             "established-directory", "local-news", "social-media", "other"],
                },
                "text_excerpt": {
                    "type": "string",
                    "description": "Verbatim text from the source containing this value (≤200 chars).",
                },
                "snapshot_url": {
                    "type": "string",
                    "description": "Wayback Machine snapshot URL — only include if wayback_check(url) returned one. Leave blank otherwise.",
                },
                "content_hash": {
                    "type": "string",
                    "description": "SHA-256 of the page text if you computed it (format: sha256:hexdigest).",
                },
                "conflicts_with": {
                    "type": "string",
                    "description": "If this value differs from a prior finding for the same field, describe the discrepancy.",
                },
            },
            "required": ["pass", "field", "value", "source_url", "source_type"],
        },
    },
}

COMPLETE_PASS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "complete_pass",
        "description": "Finalize this research pass. List all fields you could not find and any concerns.",
        "parameters": {
            "type": "object",
            "properties": {
                "pass": {"type": "string", "enum": ["A", "B"]},
                "unknown_fields":     {"type": "array", "items": {"type": "string"}, "description": "Fields you searched for but could not find."},
                "possible_duplicates":{"type": "array", "items": {"type": "string"}, "description": "Names of possibly duplicate orgs found during research."},
                "privacy_concerns":   {"type": "array", "items": {"type": "string"}, "description": "Any privacy/safety concerns (confidential location, vulnerable population data, etc.)."},
                "proposed_risk_tier": {"type": "string", "enum": ["low", "elevated", "critical"],
                                       "description": "low=standard community resource; elevated=crisis/DV/children; critical=emergency safety."},
                "limitations":        {"type": "array", "items": {"type": "string"}, "description": "Research limitations, outdated info, access issues."},
                "operating_status":   {"type": "string", "enum": ["active", "inactive", "closed", "unclear"],
                                       "description": "Your assessment of whether this org is currently operating."},
            },
            "required": ["pass", "unknown_fields", "possible_duplicates", "privacy_concerns",
                         "proposed_risk_tier", "limitations", "operating_status"],
        },
    },
}


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

def _pass_a_prompt(lead: dict, category_info: dict) -> str:
    name = lead.get("name", "")
    category = lead.get("category", "")
    address = lead.get("address", "") or ""
    city = lead.get("city", "") or ""
    state = lead.get("state", "") or ""
    phone = lead.get("phone", "") or (lead.get("phones") or [""])[0]
    url = lead.get("url", "") or ""
    source_urls = lead.get("source_urls") or []
    guidance = category_info.get("guidance", "")
    essential = category_info.get("essential", [])
    material = category_info.get("material", [])
    sensitive = category_info.get("sensitive", False)
    area = f"{city}, {state}".strip(", ")

    sensitive_note = (
        "\n⚠️  SENSITIVE CATEGORY — This may be a confidential location (DV shelter, crisis safe house).\n"
        "NEVER record a physical address if the org keeps its location confidential.\n"
        "Check their website — if it says 'call for location' or omits the address, mark coverage_scope but leave address blank.\n"
    ) if sensitive else ""

    return textwrap.dedent(f"""
    You are Research Agent A for Beacon, a community resource directory.
    Your job: verify and enrich one lead using PRIMARY sources (the org's own website + official records).

    ## Lead to investigate
    Name:     {name}
    Category: {category}
    Location: {address}, {area}
    Phone:    {phone}
    URL:      {url}
    Found at: {', '.join(source_urls[:2])}
    {sensitive_note}
    ## Category-specific guidance ({category})
    {guidance}

    ## What you must find
    ESSENTIAL (required for publication): {', '.join(essential)}
    MATERIAL (enriches the record): {', '.join(material)}

    ## Service area — ALWAYS research this
    Who does this resource actually serve geographically?
    Look for: "serving Laurel County", "residents of 40741", "within 25 miles", "we serve London and surrounding areas"
    → record_finding(field='service_area', value='<exact description>')
    Express as one of: county names (e.g. "Laurel County, KY"), ZIP codes, city names, or radius.
    Also record field='coverage_scope' with one of: county | multi-county | city | postal-code | radius | state | national

    ## Public access — ALWAYS record this for physical locations
    Is the public actually able to walk in or call to receive services?
    → record_finding(field='public_access', value='yes'|'no'|'unknown')
    → record_finding(field='access_notes', value='<any caveat about access>')
    EXAMPLES:
    - Warehouse/distribution center that ships to partner agencies → public_access='no'
    - Admin office, not a service location                        → public_access='no'
    - Open clinic, food pantry, shelter anyone can walk in        → public_access='yes'
    - Website is unclear, could not confirm                       → public_access='unknown'
    If public_access='no': still record address/phone for directory accuracy,
    but the REVIEWER will reject it — do NOT skip other fields.

    ## Your workflow — PASS A (Primary Sources)

    **DO THIS IN ORDER — record_finding after EVERY page, do not batch:**

    1. navigate to {url or "search for the org URL first"}
    2. The response shows [content_hash: sha256:...] at the top — note it
    3. Call screenshot(label="homepage") to capture the page as evidence
    4. Check Wayback: wayback_check(url) — if snapshot_url returned, include it in record_finding
    5. Read the page. For EVERY piece of info (phone, address, hours, eligibility, etc.):
       → record_finding(pass='A', source_type='org-website', field='...', value='...', 
                        text_excerpt='...', content_hash='sha256:...')
       Record IMMEDIATELY. Do not batch.
    6. Navigate to Contact, About, Services pages — screenshot + record_finding for each new fact
    7. Do ONE gov search: "{name} {area} site:.gov" — navigate top result, record any new facts
    8. Call complete_pass(pass='A', unknown_fields=[...], ...) and STOP

    Total budget for Pass A: 8 steps maximum. Stop the moment all ESSENTIAL fields are found.

    ## Available tools (use ONLY these — no other tool names exist)
    - navigate(url)          — load a webpage; response includes [content_hash: sha256:...]
    - search(query)          — web search
    - get_links()            — list links on current page
    - scroll_down()          — scroll current page
    - screenshot(label)      — save screenshot to evidence folder; include label describing the page
    - record_finding(...)    — log a verified fact with evidence
    - complete_pass(...)     — finish this pass (REQUIRED to end)
    - wayback_check(url)     — check if Wayback Machine has an existing snapshot (read-only)

    ## Rules
    - NEVER invent values. Only record what you actually read from a source.
    - Exact phone numbers and addresses — no paraphrasing.
    - If website has a "permanently closed" or "we have closed" notice: record operating_status='closed'.
    - If website is down / parked domain: note in limitations, try other sources.
    - Call screenshot(label='...') on every page you extract facts from — this is your local evidence.
    - Include the content_hash from the navigate response in every record_finding call.
    - **STOP SEARCHING** if you try the same field 3 times and still can't find it.
      Add it to unknown_fields and call complete_pass() immediately.
    - **MANDATORY STOP RULE**: The moment you have recorded a value for every ESSENTIAL field
      listed above, call complete_pass(pass='A', ...) on your NEXT action. Do not navigate
      another page. Do not search again. Call complete_pass() — that is your only allowed move.
    - If essential fields are still missing after 8 steps, call complete_pass() anyway and list
      them in unknown_fields. The Pass B agent will find them independently.
    """).strip()


def _pass_b_prompt(lead: dict, pass_a_findings: list[dict], category_info: dict) -> str:
    name = lead.get("name", "")
    category = lead.get("category", "")
    city = lead.get("city", "") or ""
    state = lead.get("state", "") or ""
    area = f"{city}, {state}".strip(", ")
    guidance = category_info.get("guidance", "")

    # Summarize Pass A to orient Pass B
    found_fields = sorted({f["field"] for f in pass_a_findings})
    found_values = {f["field"]: f["value"] for f in pass_a_findings}

    field_summary = "\n".join(
        f"  {field}: {str(found_values[field])[:80]}"
        for field in found_fields
    ) or "  (none yet — Pass A found nothing)"

    return textwrap.dedent(f"""
    You are Research Agent B for Beacon, a community resource directory.
    Your job: INDEPENDENTLY corroborate the lead using secondary sources.
    You must NOT simply re-check the same sources Pass A used. Find different, independent evidence.

    ## Lead to investigate
    Name:     {name}
    Category: {category}
    Location: {area}

    ## What Pass A already found (for reference — find independent confirmation, don't copy these)
    {field_summary}

    ## Category-specific guidance ({category})
    {guidance}

    ## Your workflow — PASS B (Corroborating Sources)

    **DO THIS IN ORDER — find 2 independent sources, record everything, then stop:**

    1. Search: "{name} {area} 211" → navigate to the 211/findhelp/uwbg211 listing
       → note the [content_hash: sha256:...] from the page response
       → screenshot(label="211-listing")
       → record_finding for each field (pass='B', source_type='established-directory', content_hash='sha256:...')
    2. Search: "{name} {area}" on feedingky.org or the county health dept directory
       → navigate → screenshot → record_finding with content_hash
    3. Look for service area in whatever you find: county served, ZIP codes, city boundaries, radius.
       → If Pass A didn't find service_area, record it now: record_finding(field='service_area', value='...')
    4. Search: "{name} {area} closed 2025 OR 2026" — if closure found, record operating_status='closed'
    5. Call complete_pass(pass='B', ...) and STOP

    5 steps maximum. The content_hash from navigate is your evidence integrity — include it in every record_finding.
    The goal is independent corroboration of phone/address/hours/service_area — not exhaustive research.

    ## Available tools (use ONLY these)
    - navigate(url)          — load a webpage; response includes [content_hash: sha256:...]
    - search(query)          — web search
    - get_links()            — list links on current page
    - screenshot(label)      — save screenshot to evidence folder
    - record_finding(...)    — log a verified fact with evidence
    - complete_pass(...)     — finish this pass (REQUIRED)
    - wayback_check(url)     — check if Wayback Machine has an existing snapshot (read-only)

    ## Rules
    - Do NOT re-use sources from Pass A (org's own website, same directory)
    - NEVER invent values
    - If you find a conflicting value, record both and set conflicts_with
    - Call screenshot(label='...') on every corroborating page you extract facts from
    - Include the content_hash from the navigate response in each record_finding call
    - **STOP SEARCHING** after 3 failed attempts on the same field — add to unknown_fields.
    - **MANDATORY STOP RULE**: After visiting 2 independent sources, call complete_pass(pass='B', ...)
      on your NEXT action. Do not visit a third source unless the first two gave zero useful data.
    - Maximum 5 steps total for Pass B. If you reach step 5 without calling complete_pass, do it now.
    """).strip()


# ---------------------------------------------------------------------------
# Investigation store — accumulates findings across both passes
# ---------------------------------------------------------------------------

class InvestigationStore:
    def __init__(self, lead: dict):
        self.lead = lead
        self.findings: list[dict] = []
        self.pass_completions: dict[str, dict] = {}
        self._ev_counter = 0

    def next_ev_id(self, pass_: str) -> str:
        self._ev_counter += 1
        return f"ev-{pass_.lower()}-{self._ev_counter:03d}"

    async def handle_record_finding(self, args: dict) -> str:
        pass_ = args.get("pass", "A")
        field = args.get("field", "")
        value = args.get("value")
        source_url = args.get("source_url", "")
        source_type = args.get("source_type", "other")

        ev_id = self.next_ev_id(pass_)
        finding = {
            "ev_id":        ev_id,
            "pass":         pass_,
            "field":        field,
            "value":        value,
            "source_url":   source_url,
            "source_type":  source_type,
            "text_excerpt": args.get("text_excerpt"),
            "snapshot_url": args.get("snapshot_url"),
            "content_hash": args.get("content_hash"),
            "conflicts_with": args.get("conflicts_with"),
            "retrieved_at": date.today().isoformat(),
        }
        self.findings.append(finding)
        log.info("  finding [%s] %s → %s (from %s)",
                 ev_id, field, str(value)[:60], source_type)
        return json.dumps({"recorded": ev_id, "field": field})

    async def handle_complete_pass(self, args: dict) -> str:
        pass_ = args.get("pass", "A")
        self.pass_completions[pass_] = {
            "pass":              pass_,
            "locked_at":         datetime.now(timezone.utc).isoformat(),
            "unknown_fields":    args.get("unknown_fields", []),
            "possible_duplicates": args.get("possible_duplicates", []),
            "privacy_concerns":  args.get("privacy_concerns", []),
            "proposed_risk_tier": args.get("proposed_risk_tier", "low"),
            "limitations":       args.get("limitations", []),
            "operating_status":  args.get("operating_status", "active"),
        }
        n = len([f for f in self.findings if f["pass"] == pass_])
        log.info("  pass %s complete — %d findings, operating_status=%s",
                 pass_, n, args.get("operating_status"))
        return json.dumps({"locked": True, "pass": pass_, "findings": n})

    def tool_schemas(self) -> list[dict]:
        return [RECORD_FINDING_SCHEMA, COMPLETE_PASS_SCHEMA, WAYBACK_CHECK_SCHEMA]

    def tool_handlers(self) -> dict:
        return {
            "record_finding": self.handle_record_finding,
            "complete_pass":  self.handle_complete_pass,
            "wayback_check":  handle_wayback_check,
        }

    def to_investigation_result(self) -> dict:
        """Produce the final structured investigation output."""
        return {
            "lead_id":           _lead_id(self.lead),
            "investigated_at":   datetime.now(timezone.utc).isoformat(),
            "lead":              self.lead,
            "findings":          self.findings,
            "pass_a":            self.pass_completions.get("A", {}),
            "pass_b":            self.pass_completions.get("B", {}),
            "summary": {
                "total_findings": len(self.findings),
                "pass_a_count":   len([f for f in self.findings if f["pass"] == "A"]),
                "pass_b_count":   len([f for f in self.findings if f["pass"] == "B"]),
                "fields_found":   sorted({f["field"] for f in self.findings}),
                "conflicts":      [f for f in self.findings if f.get("conflicts_with")],
                "operating_status": (
                    self.pass_completions.get("B", {}).get("operating_status") or
                    self.pass_completions.get("A", {}).get("operating_status") or
                    "unclear"
                ),
                "risk_tier": (
                    self.pass_completions.get("B", {}).get("proposed_risk_tier") or
                    self.pass_completions.get("A", {}).get("proposed_risk_tier") or
                    "low"
                ),
            },
        }


# ---------------------------------------------------------------------------
# Main investigation runner
# ---------------------------------------------------------------------------

def _checkpoint(store: "InvestigationStore", lead: dict) -> None:
    """Write a partial investigation result to disk after Pass A."""
    try:
        result = store.to_investigation_result()
        out_dir = INVESTIGATIONS_DIR / lead.get("zip", "unknown")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{_lead_id(lead)}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        log.info("checkpoint saved → %s", out_path.relative_to(BEACON_ROOT))
    except Exception as e:
        log.warning("checkpoint failed: %s", e)



async def investigate(lead: dict, *, max_steps_per_pass: int = 20) -> dict:
    """Run two-pass investigation on a lead. Returns investigation result dict."""
    category = lead.get("category", "community")
    cat_info = _CATEGORY_FIELDS.get(category, _CATEGORY_FIELDS["community"])
    store = InvestigationStore(lead)

    log.info("=== investigating: %s (%s) ===", lead.get("name"), category)

    evidence_dir = INVESTIGATIONS_DIR / lead.get("zip", "unknown") / f"{_lead_id(lead)}-evidence"
    async with BrowserSession(evidence_dir=evidence_dir) as browser:
        async with SearchSession() as search:
            browser_schemas, browser_handlers = session_tools(browser, search)

            all_schemas   = browser_schemas + store.tool_schemas()
            all_handlers  = {**browser_handlers, **store.tool_handlers()}

            # --- Pass A: primary sources ---
            log.info("--- Pass A: primary sources ---")
            system_a = _pass_a_prompt(lead, cat_info)
            user_a = (
                f"Investigate '{lead.get('name')}' in {lead.get('city', '')}, "
                f"{lead.get('state', '')}. Run Pass A now."
            )
            await agent.run(
                system=system_a,
                user=user_a,
                tools=all_schemas,
                extra_handlers=all_handlers,
                max_steps=max_steps_per_pass,
            )

            # Checkpoint after Pass A so a timeout doesn't lose all work
            _checkpoint(store, lead)

            # --- Pass B: corroborating sources ---
            log.info("--- Pass B: corroborating sources ---")
            pass_a_findings = [f for f in store.findings if f["pass"] == "A"]
            system_b = _pass_b_prompt(lead, pass_a_findings, cat_info)
            user_b = (
                f"You are Research Agent B. Independently corroborate "
                f"'{lead.get('name')}' using different sources. Run Pass B now."
            )
            await agent.run(
                system=system_b,
                user=user_b,
                tools=all_schemas,
                extra_handlers=all_handlers,
                max_steps=max_steps_per_pass,
            )

    result = store.to_investigation_result()

    # Save investigation to disk
    out_dir = INVESTIGATIONS_DIR / lead.get("zip", "unknown")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_lead_id(lead)}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    log.info("saved investigation → %s", out_path.relative_to(BEACON_ROOT))

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lead_id(lead: dict) -> str:
    """Stable slug for the lead."""
    name = re.sub(r"[^a-z0-9]+", "-", (lead.get("name") or "unknown").lower()).strip("-")
    zip_ = lead.get("zip") or lead.get("found_in_zip") or "00000"
    return f"{zip_}-{name}"[:80]


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
    p = argparse.ArgumentParser(description="Investigate a lead")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--json",  help="Lead as inline JSON string")
    g.add_argument("--file",  help="Path to raw run JSON; use --name to select one lead")
    g.add_argument("lead_key", nargs="?", help="dedup_key from leads/dedup.json")
    p.add_argument("--name", help="Org name filter when --file is used")
    args = p.parse_args()

    lead = None

    if args.json:
        lead = json.loads(args.json)

    elif args.file:
        run = json.loads(Path(args.file).read_text())
        resources = run.get("resources_found", []) or []
        if args.name:
            matches = [r for r in resources if args.name.lower() in r.get("name","").lower()]
            if not matches:
                print(f"No lead matching '{args.name}' in {args.file}", file=sys.stderr)
                sys.exit(1)
            lead = matches[0]
        else:
            lead = resources[0] if resources else None
            if not lead:
                print("File has no resources_found", file=sys.stderr)
                sys.exit(1)

    elif args.lead_key:
        import sys; sys.path.insert(0, str(BEACON_ROOT / "leads"))
        dedup = json.loads((BEACON_ROOT / "leads" / "dedup.json").read_text())
        discovered = dedup.get("discovered", {})
        key = args.lead_key
        if key not in discovered:
            print(f"Key not found in dedup.json: {key}", file=sys.stderr)
            sys.exit(1)
        lead = {"name": discovered[key]["name"], **discovered[key]}

    result = await investigate(lead)
    print(json.dumps({
        "lead_id":   result["lead_id"],
        "fields_found": result["summary"]["fields_found"],
        "operating_status": result["summary"]["operating_status"],
        "total_findings": result["summary"]["total_findings"],
        "conflicts": len(result["summary"]["conflicts"]),
        "output": str(INVESTIGATIONS_DIR / lead.get("zip","unknown") / f"{result['lead_id']}.json"),
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
