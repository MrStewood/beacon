"""
Candidate Builder
=================
Converts a structured investigation result (from investigate.py) into a
candidate YAML file at source/candidates/<county>/<id>.yaml, then calls
scripts/sign_candidate.py to deterministically score and sign it.

Usage
-----
    python -m app.pipeline.candidate leads/investigations/40744/40744-gods-pantry.json
    python -m app.pipeline.candidate --investigate leads/runs/40744/run-raw.json --name "God's Pantry"
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

BEACON_ROOT = Path(__file__).resolve().parents[2]
CANDIDATES_DIR = BEACON_ROOT / "source" / "candidates"

# Maps source_type → evidence tier (A–F)
_TIER: dict[str, str] = {
    "org-website":           "A",
    "gov-directory":         "B",
    "state-database":        "B",
    "established-directory": "C",
    "local-news":            "D",
    "social-media":          "E",
    "other":                 "E",
}

# Maps source_type → directness int (schema enum: 0|8|15|20)
_DIRECTNESS: dict[str, int] = {
    "org-website":           20,
    "gov-directory":         15,
    "state-database":        15,
    "established-directory": 15,
    "local-news":             8,
    "social-media":           8,
    "other":                  0,
}

# Maps field → freshness_class
_FRESHNESS_CLASS: dict[str, str] = {
    "operating_status":  "operating_status",
    "phone":             "hours_phone",
    "hours":             "hours_phone",
    "address":           "address",
    "eligibility":       "eligibility",
    "what_to_bring":     "eligibility",
    "cost":              "eligibility",
    "intake_process":    "eligibility",
    "description":       "service_description",
    "service_types":     "service_description",
    "populations":       "service_description",
    "languages":         "service_description",
    "capacity":          "service_description",
    "url":               "stable_program_identity",
    "email":             "stable_program_identity",
    "facebook":          "stable_program_identity",
    "coverage_scope":    "stable_program_identity",
}

# Which fields are always essential regardless of category
_ALWAYS_ESSENTIAL = {"operating_status", "phone", "address"}

# Policy version must match scripts/trust_scoring.py POLICY_VERSION
POLICY_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_candidate(investigation_path: Path) -> Path:
    """Load investigation JSON and write candidate YAML. Returns the YAML path."""
    result = json.loads(investigation_path.read_text())
    lead   = result["lead"]
    name   = lead.get("name", "unknown")
    county = lead.get("county", "unknown").lower()
    zip_   = lead.get("zip") or lead.get("found_in_zip") or "00000"
    category = lead.get("category", "community")

    candidate_id = _candidate_id(name, county, zip_)
    log.info("building candidate %s", candidate_id)

    # Determine risk tier (elevated/critical for sensitive categories)
    risk_tier = _risk_tier(category, result)

    # Build claims from findings
    claims = _build_claims(result["findings"], category, risk_tier)

    # Build research packages
    research_packages = _build_research_packages(result, candidate_id)

    # Build resource proposal
    resource = _build_resource(result, candidate_id, category)

    # Detect conflicts
    conflicts = _build_conflicts(result["findings"])

    # Assemble candidate
    candidate = {
        "candidate_id":   candidate_id,
        "policy_version": POLICY_VERSION,
        "workflow_state": "research-b-locked",
        "risk_tier":      risk_tier,
        "lead": {
            "source_type": "search-result",
            "received_at": lead.get("found_at", date.today().isoformat())[:10],
            "description": f"Discovered during ZIP {zip_} research run",
        },
        "resource":           resource,
        "claims":             claims,
        "research_packages":  research_packages,
        **({"conflicts": conflicts} if conflicts else {}),
        "audit": [
            {
                "state":      "lead-received",
                "actor":      "lead-generation-agent",
                "actor_role": "research-a",
                "at":         lead.get("found_at", _utc_now()),
            },
            {
                "state":      "research-b-locked",
                "actor":      "investigation-agent",
                "actor_role": "research-b",
                "at":         result.get("investigated_at", _utc_now()),
            },
        ],
    }

    # Write YAML
    out_dir = CANDIDATES_DIR / county
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{candidate_id}.yaml"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Beacon candidate — {name}\n")
        f.write(f"# Generated: {_utc_now()}\n")
        f.write(f"# Source: {investigation_path.resolve().relative_to(BEACON_ROOT)}\n\n")
        yaml.dump(candidate, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False, width=120)

    log.info("wrote candidate → %s", out_path.relative_to(BEACON_ROOT))

    # Sign: call scripts/sign_candidate.py to score + add decision block
    _sign(out_path)

    return out_path


# ---------------------------------------------------------------------------
# Claims builder
# ---------------------------------------------------------------------------

def _build_claims(findings: list[dict], category: str, risk_tier: str) -> list[dict]:
    """Group findings by field, build claim objects with evidence lists."""
    from collections import defaultdict

    # Group by field
    by_field: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_field[f["field"]].append(f)

    # Determine essential/material per category
    from app.pipeline.investigate import _CATEGORY_FIELDS
    cat_info = _CATEGORY_FIELDS.get(category, _CATEGORY_FIELDS["community"])
    essential_fields = set(cat_info.get("essential", [])) | _ALWAYS_ESSENTIAL
    material_fields  = set(cat_info.get("material", []))

    claims = []
    claim_num = 0

    # Always include operating_status even if not explicitly found
    all_fields = list(by_field.keys())
    if "operating_status" not in all_fields:
        all_fields = ["operating_status"] + all_fields

    for field in all_fields:
        field_findings = by_field.get(field, [])
        claim_num += 1
        claim_id = f"cl-{claim_num:03d}-{field.replace('_','-')}"

        # Determine consensus value (most common non-conflicting value)
        # Separate supporting vs conflicting evidence
        supporting = [f for f in field_findings if not f.get("conflicts_with")]
        conflicting = [f for f in field_findings if f.get("conflicts_with")]

        # Use Pass A value as primary, or first supporting value
        primary = next((f for f in supporting if f["pass"] == "A"), None) or \
                  next(iter(supporting), None) or \
                  next(iter(field_findings), None)

        value = primary["value"] if primary else None

        # operating_status special case
        if field == "operating_status" and value is None:
            value = "active"  # assume active if we found enough info to build a claim

        freshness = _FRESHNESS_CLASS.get(field, "service_description")
        essential = field in essential_fields
        material  = field in material_fields or field in essential_fields

        # Build evidence list
        evidence = []
        seen_chains: set[str] = set()

        # Source types that are definitionally independent of each other —
        # an org's own website, a government registry, and a 211 database
        # are run by different organizations with no shared data pipeline.
        _KNOWN_INDEPENDENT = frozenset({
            "org-website", "gov-directory", "state-database", "established-directory"
        })

        for finding in field_findings:
            source_type = finding.get("source_type", "other")
            chain_id = _chain_id(finding["source_url"])

            # chain_independence_known: True when the source type itself guarantees
            # independence from other known-independent source types.
            chain_independence_known = source_type in _KNOWN_INDEPENDENT
            seen_chains.add(chain_id)

            ev = {
                "id":            finding["ev_id"],
                "url":           finding["source_url"],
                "source_type":   source_type,
                "tier":          _TIER.get(source_type, "E"),
                "directness":    _DIRECTNESS.get(source_type, 0),
                "retrieved_at":  finding.get("retrieved_at", date.today().isoformat()),
                "chain_id":      chain_id,
                "chain_independence_known": chain_independence_known,
                "supports":      not bool(finding.get("conflicts_with")),
                "reopenable":    True,
            }
            if finding.get("text_excerpt"):
                ev["excerpt"] = finding["text_excerpt"][:200]
            if finding.get("snapshot_url"):
                ev["archived_snapshot"] = finding["snapshot_url"]
            if finding.get("content_hash"):
                ev["content_hash"] = finding["content_hash"]

            evidence.append(ev)

        if not evidence:
            # Bare claim with no evidence — scores 0, status not-found
            evidence = []

        claim = {
            "claim_id":       claim_id,
            "field":          field,
            "value":          value,
            "essential":      essential,
            "material":       material,
            "freshness_class": freshness,
            "evidence":       evidence,
        }
        if conflicting:
            claim["_has_conflict"] = True  # flag for human review; stripped from signature

        claims.append(claim)

    return claims


# ---------------------------------------------------------------------------
# Research packages builder
# ---------------------------------------------------------------------------

def _build_research_packages(result: dict, candidate_id: str) -> list[dict]:
    findings = result["findings"]
    pass_a_comp = result.get("pass_a", {})
    pass_b_comp = result.get("pass_b", {})

    def _pkg(pass_: str, comp: dict, researcher_role: str) -> dict:
        claimed = sorted({f["field"] for f in findings if f["pass"] == pass_})
        return {
            "researcher":         researcher_role,
            "locked_at":          comp.get("locked_at", _utc_now()),
            "proposed_claims":    claimed,
            "unknown_fields":     comp.get("unknown_fields", []),
            "possible_duplicates":comp.get("possible_duplicates", []),
            "privacy_concerns":   comp.get("privacy_concerns", []),
            "proposed_risk_tier": comp.get("proposed_risk_tier", "low"),
            "limitations":        comp.get("limitations", []),
        }

    return [
        _pkg("A", pass_a_comp, "research-agent-a"),
        _pkg("B", pass_b_comp, "research-agent-b"),
    ]


# ---------------------------------------------------------------------------
# Resource proposal builder
# ---------------------------------------------------------------------------

def _build_resource(result: dict, candidate_id: str, category: str) -> dict:
    lead     = result["lead"]
    findings = result["findings"]
    summary  = result.get("summary", {})

    # Build field lookup from findings (prefer Pass A, then B)
    field_val: dict[str, Any] = {}
    for f in findings:
        if f["field"] not in field_val or f["pass"] == "A":
            if not f.get("conflicts_with"):
                field_val[f["field"]] = f["value"]

    # Fall back to lead fields for anything not found in investigation
    def _get(field: str, default: Any = None) -> Any:
        return field_val.get(field) or lead.get(field) or default

    name     = _get("name") or lead.get("name", "")
    phone    = _get("phone") or (lead.get("phones") or [""])[0]
    phones   = list({p for p in [phone] + (lead.get("phones") or []) if p})
    address  = _get("address") or lead.get("address", "")
    city     = lead.get("city", "")
    state    = lead.get("state", "")
    zip_     = lead.get("zip") or lead.get("found_in_zip") or ""
    county   = lead.get("county", "")
    url      = _get("url") or lead.get("url", "")
    hours    = _get("hours")
    eligibility = _get("eligibility")
    cost     = _get("cost")
    # Description: prefer the shortest Pass-A finding that mentions the org's services,
    # not org-history or SOS-profile boilerplate. If multiple description findings
    # exist, pick the one that best describes what the location does.
    _desc_findings = [f["value"] for f in findings if f["field"] == "description" and f["pass"] == "A"]
    if _desc_findings:
        # Prefer findings that mention "food", "serve", "provide", "pantry", "shelter" etc.
        _SERVICE_WORDS = {"food", "serve", "provid", "pantry", "shelter", "clinic", "assist", "help"}
        _desc_findings.sort(key=lambda s: (
            -sum(1 for w in _SERVICE_WORDS if w in s.lower()),
            len(s)  # prefer shorter when score ties
        ))
        description = _desc_findings[0]
    else:
        description = _get("description") or lead.get("description", "")

    # public_access: yes/no/unknown — determines publishability
    public_access = str(_get("public_access") or "unknown").lower().strip()
    access_notes  = _get("access_notes") or ""

    populations = _get("populations") or lead.get("populations") or []
    service_types = _get("service_types") or lead.get("service_types") or []
    languages = _get("languages") or []
    coverage_scope = _get("coverage_scope") or "county"
    service_area_raw = _get("service_area")   # agent's free-text finding
    operating_status = summary.get("operating_status", "active")

    # Location: schema v3 uses flat fields (address_line_1, city, state, postal_code)
    # NOT a nested address object. phones/hours/email belong at resource top level.
    location: dict[str, Any] = {
        "id":            f"{candidate_id}-loc-1",
        "location_type": "physical",
        "publicly_displayed": True,
    }
    if address:
        location["address_line_1"] = address
    if city:
        location["city"] = city
    if state:
        location["state"] = state
    if zip_:
        location["postal_code"] = zip_
    if county:
        location["county_name"] = county

    # Normalize service_types: must be array of valid enum values, not free text
    _VALID_SVC = {
        "hotline","walk-in","appointment","residential","outpatient",
        "mobile","online","peer-led","faith-based","government",
    }
    raw_svc = _get("service_types") or lead.get("service_types") or []
    if isinstance(raw_svc, str):
        # Agent returned a description string — extract any valid tokens
        raw_svc = [s.strip() for s in raw_svc.replace(";",",").split(",")]
    clean_svc = [s for s in raw_svc if s in _VALID_SVC]

    # Normalize phones: deduplicate, keep formatted versions
    import re as _re
    seen_digits: set[str] = set()
    clean_phones: list[str] = []
    for p in phones:
        digits = _re.sub(r"\D", "", str(p))[-10:]
        if digits and digits not in seen_digits:
            seen_digits.add(digits)
            formatted = _re.sub(r"(\d{3})(\d{3})(\d{4})", r"(\1) \2-\3", digits)
            clean_phones.append(formatted)

    # Source URLs for traceability
    all_source_urls = list({
        f.get("source_url", "") for f in findings
        if f.get("source_url")
    })

    resource: dict[str, Any] = {
        "id":                  candidate_id,
        "name":                name,
        "status":              "active" if operating_status == "active" else "inactive",
        "coverage_scope":      coverage_scope,
        "needs":               [category],
        "locations":           [location],
        "verification_status": "verified",
        "last_verified":       _utc_now()[:10],
        "verified_by":         "investigation-agent",
        "confidence":          "medium",
        # Publishability gate — reviewer hard-checks this
        "public_access":       public_access,   # yes | no | unknown
    }
    if access_notes:
        resource["access_notes"] = access_notes
    if clean_phones:
        resource["phones"] = clean_phones
    if url:
        resource["url"] = url
    if hours:
        resource["hours"] = hours
    if description:
        resource["description"] = description
    if eligibility:
        resource["eligibility"] = eligibility
    if cost:
        _cost_norm = str(cost).lower()
        if "free" in _cost_norm or "no cost" in _cost_norm or "no charge" in _cost_norm:
            resource["cost"] = "free"
        elif "sliding" in _cost_norm:
            resource["cost"] = "sliding-scale"
        elif "insurance" in _cost_norm:
            resource["cost"] = "insurance"
        elif "private" in _cost_norm or "pay" in _cost_norm:
            resource["cost"] = "private-pay"
        else:
            resource["cost"] = "unknown"
    _VALID_POPULATIONS = {
        "anyone", "families", "women", "men", "youth", "seniors",
        "veterans", "lgbtq+", "disability", "re-entry", "pregnant",
        "substance-use", "recovery",
    }
    if populations:
        if isinstance(populations, str):
            populations = [populations]
        resource["populations"] = [p for p in populations if p in _VALID_POPULATIONS]
    if languages:
        resource["languages"] = languages
    if _get("email"):
        resource["email"] = _get("email")
    if _get("what_to_bring"):
        resource["what_to_bring"] = _get("what_to_bring")
    if _get("intake_process"):
        resource["intake_process"] = _get("intake_process")
    if all_source_urls:
        resource["source_urls"] = all_source_urls[:5]

    # Service areas — prefer agent-found, fall back to derivation from coverage_scope
    _svc_areas = _parse_service_area(
        service_area_raw,
        state or lead.get("state", ""),
        county or lead.get("county", ""),
    )
    if _svc_areas:
        resource["service_areas"] = _svc_areas

    return resource


def _parse_service_area(raw: str, state: str, county_name: str) -> list[dict]:
    """Convert agent free-text service_area finding into schema service_areas[].

    Recognises (in order of specificity):
      radius   — "within 25 miles", "25-mile radius"
      zip      — "40741", "40741 and 40742"
      county   — "Laurel County, KY", "Laurel, Clay, and Whitley Counties"
      city     — "London KY", "London and surrounding areas"
    Falls back to the known county_name if nothing else matches.
    """
    import re as _re

    if not raw:
        if county_name and state:
            return [{"type": "county", "state": state, "country": "US",
                     "values": [{"name": county_name}]}]
        return []

    text = str(raw).strip()

    # --- Radius ---
    radius_m = _re.search(r"(\d+)\s*[\-\u2013]?\s*mile", text, _re.I)
    if radius_m:
        return [{"type": "radius", "radius_miles": int(radius_m.group(1))}]

    # --- ZIP codes (5-digit sequences) ---
    zips = _re.findall(r"(?<![\d])(\d{5})(?![\d])", text)
    if zips:
        return [{
            "type": "postal-code",
            "state": state or "KY",
            "country": "US",
            "values": [{"name": z} for z in zips],
        }]

    # --- County names (matches "Laurel County" and "Laurel, Clay, and Whitley Counties") ---
    # First try plural form — captures comma-separated county names before "Counties"
    plural_m = _re.search(r"([A-Za-z,\s]+)\s+[Cc]ounties", text)
    if plural_m:
        raw_names = _re.split(r",|\band\b", plural_m.group(1), flags=_re.I)
        names = [n.strip().rstrip(",") for n in raw_names if n.strip()]
        if names:
            return [{
                "type": "county",
                "state": state or "KY",
                "country": "US",
                "values": [{"name": n} for n in names if n],
            }]
    # Singular "County"
    singular_m = _re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+[Cc]ounty", text)
    if singular_m:
        return [{
            "type": "county",
            "state": state or "KY",
            "country": "US",
            "values": [{"name": c.strip()} for c in singular_m],
        }]

    # --- City / town (first proper noun before KY/Kentucky/and/comma) ---
    city_m = _re.match(r"^([A-Z][a-zA-Z\s]+?)(?:\s+(?:KY|Kentucky|and)|,|$)", text)
    if city_m:
        city_cand = city_m.group(1).strip()
        skip = ("county", "mile", "area", "state", "national", "serves", "surrounding")
        if len(city_cand.split()) <= 4 and not any(w in city_cand.lower() for w in skip):
            return [{
                "type": "city",
                "state": state or "KY",
                "country": "US",
                "values": [{"name": city_cand}],
            }]

    # --- Fallback: county from location ---
    if county_name and state:
        return [{"type": "county", "state": state, "country": "US",
                 "values": [{"name": county_name}]}]
    return []


# ---------------------------------------------------------------------------
# Conflicts builder
# ---------------------------------------------------------------------------

def _build_conflicts(findings: list[dict]) -> list[dict]:
    conflicts = []
    for f in findings:
        if f.get("conflicts_with"):
            # Classify conflict kind
            field = f.get("field", "")
            if field in ("phone", "address"):
                kind = "phone-address-status"
            elif field in ("hours", "eligibility", "cost"):
                kind = "hours-eligibility-coverage"
            else:
                kind = "wording"

            conflicts.append({
                "claim_id":                f"conflict-{f['ev_id']}",
                "kind":                    kind,
                "values":                  [f["value"], f["conflicts_with"]],
                "resolution":              "unresolved",
                "rejected_values_preserved": True,
                "note":                    f["conflicts_with"],
            })
    return conflicts


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def _sign(yaml_path: Path) -> None:
    """Call scripts/sign_candidate.py to score and sign the candidate."""
    sign_script = BEACON_ROOT / "scripts" / "sign_candidate.py"
    if not sign_script.exists():
        log.warning("sign_candidate.py not found — candidate unsigned")
        return
    result = subprocess.run(
        [sys.executable, str(sign_script), str(yaml_path)],
        capture_output=True, text=True, cwd=str(BEACON_ROOT),
    )
    if result.returncode != 0:
        log.error("sign_candidate.py failed:\n%s", result.stderr[:500])
    else:
        log.info("signed: %s", yaml_path.name)
        if result.stdout.strip():
            try:
                out = json.loads(result.stdout)
                log.info("  score=%s outcome=%s",
                         out.get("record_trust_score"), out.get("outcome"))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate_id(name: str, county: str, zip_: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-",
                  f"{county}-{name}".lower()).strip("-")[:60]
    # Append short hash to guarantee uniqueness
    h = hashlib.sha256(f"{name}:{zip_}".encode()).hexdigest()[:6]
    return f"{slug}-{h}"


def _chain_id(url: str) -> str:
    """Assign a chain_id based on the domain — same domain = same upstream chain."""
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # Known shared chains
    if "211" in host or "uwbg" in host or "findhelp" in host:
        return "211-network"
    if "feedingamerica" in host or "feedingky" in host or "feedam" in host:
        return "feeding-america"
    if "needhelppayingbills" in host or "rentassistance" in host:
        return "bill-assistance-aggregator"
    if ".gov" in host:
        return f"gov-{host}"
    return host or "unknown"


def _risk_tier(category: str, result: dict) -> str:
    """Assign risk tier based on category and investigation findings."""
    from app.pipeline.investigate import _CATEGORY_FIELDS
    cat_info = _CATEGORY_FIELDS.get(category, {})
    if cat_info.get("sensitive"):
        return "elevated"
    if category in ("crisis",):
        return "elevated"
    # Check for confidential address flags in pass completions
    for pkg in [result.get("pass_a", {}), result.get("pass_b", {})]:
        if pkg.get("privacy_concerns"):
            return "elevated"
    return "low"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    import argparse

    p = argparse.ArgumentParser(description="Build a candidate YAML from an investigation JSON")
    p.add_argument("investigation", help="Path to investigation JSON file")
    args = p.parse_args()

    path = Path(args.investigation)
    if not path.exists():
        print(f"Not found: {path}", file=sys.stderr)
        sys.exit(1)

    out = build_candidate(path)
    print(f"Candidate written: {out}")
