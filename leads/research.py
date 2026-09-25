#!/usr/bin/env python3
"""Beacon Lead Discovery — ZIP-based community resource research tool.

Usage:
    python3 leads/research.py prompt 40701
    python3 leads/research.py plan 40701
    python3 leads/research.py process 40701 results.json [--dry-run]
    python3 leads/research.py status
    python3 leads/research.py leads
    python3 leads/research.py out-of-area
    python3 leads/research.py needs 40701
    python3 leads/research.py needs KY
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BEACON_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BEACON_ROOT / "data"
SOURCE_DIR = BEACON_ROOT / "source"
PILOT_DIR = BEACON_ROOT / "pilot"
CASES_DIR = PILOT_DIR / "cases"
REJECTED_DIR = PILOT_DIR / "rejected"
LEADS_DIR = BEACON_ROOT / "leads"
RUNS_DIR = LEADS_DIR / "runs"
DEDUP_PATH = LEADS_DIR / "dedup.json"
PROMPT_TEMPLATE = LEADS_DIR / "search_prompt.md"
CENSUS_ZIPS_PATH = DATA_DIR / "census" / "us-zips.json"

_census_zips: dict[str, Any] | None = None

CATEGORIES = [
    "food", "shelter", "housing", "health", "mental-health",
    "addiction", "crisis", "family", "legal", "documents",
    "education", "jobs", "transportation", "utility-assistance",
    "clothing", "community", "veterans",
]

TERMINAL_CLASSIFICATIONS = {
    "duplicate_existing_resource",
    "duplicate_existing_case",
    "duplicate_existing_lead",
    "duplicate_prior_run",
    "previously_rejected",
    "insufficient_info",
    "policy_rejected",
}

REVIEW_CLASSIFICATIONS = {
    "near_duplicate_review",
    "possible_related_program",
    "reconsider_rejected",
}


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_census_zips() -> dict[str, Any]:
    global _census_zips
    if _census_zips is None:
        _census_zips = load_json(CENSUS_ZIPS_PATH, {})
    return _census_zips


def resolve_zip(zip_code: str) -> dict[str, str]:
    z = re.sub(r"\D", "", zip_code).zfill(5)
    zips = _load_census_zips()
    entry = zips.get(z)
    if entry is None:
        return {"zip": z, "county": "Unknown", "state": "Unknown", "city": "Unknown"}
    if isinstance(entry, dict) and entry.get("_multi_county"):
        first = entry["counties"][0]
        return {"zip": z, "county": first["county"], "state": first["state"], "city": first["city"]}
    if isinstance(entry, dict):
        return {
            "zip": z,
            "county": entry.get("county", "Unknown"),
            "state": entry.get("state", "Unknown"),
            "city": entry.get("city", "Unknown"),
        }
    return {"zip": z, "county": "Unknown", "state": "Unknown", "city": "Unknown"}


def make_run_id(zip_code: str) -> str:
    return f"leadgen-{zip_code}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


# ---------------------------------------------------------------------------
# Normalization and identity
# ---------------------------------------------------------------------------

def _normalize_name(name: str | None) -> str:
    n = (name or "").lower().strip()
    n = n.replace("&", " and ")
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n)
    for suffix in [
        "inc", "llc", "ltd", "corp", "co", "company", "corporation",
        "nonprofit", "non profit", "organization", "ministries", "ministry",
        "of ky", "of kentucky", "of eastern ky", "of eastern kentucky",
    ]:
        n = re.sub(rf"\b{re.escape(suffix)}\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def _normalize_phone(phone: str | None) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _normalize_domain(url: str | None) -> str:
    if not url:
        return ""
    raw = url.strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    host = urlparse(raw).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _canonical_url(url: str | None) -> str:
    if not url:
        return ""
    raw = url.strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


def _normalize_address(address: str | None) -> str:
    a = (address or "").lower().strip()
    a = re.sub(r"[^a-z0-9\s]", " ", a)
    replacements = {
        "street": "st", "avenue": "ave", "road": "rd", "drive": "dr",
        "boulevard": "blvd", "highway": "hwy", "suite": "ste", "kentucky": "ky",
    }
    parts = [replacements.get(p, p) for p in a.split()]
    return " ".join(parts)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _phones(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(_as_list(record.get("phones")))
    values.extend(_as_list(record.get("phone")))
    values.extend(_as_list(record.get("proposed_phone")))
    return sorted({p for p in (_normalize_phone(str(v)) for v in values) if p})


def _urls(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("url", "website", "source_url", "proposed_url"):
        values.extend(_as_list(record.get(key)))
    values.extend(_as_list(record.get("source_urls")))
    return sorted({_canonical_url(str(v)) for v in values if _canonical_url(str(v))})


def _domains(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("url", "website", "source_url", "proposed_url"):
        values.extend(_as_list(record.get(key)))
    values.extend(_as_list(record.get("source_urls")))
    return sorted({_normalize_domain(str(v)) for v in values if _normalize_domain(str(v))})


def _addresses(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("address", "proposed_address"):
        values.extend(_as_list(record.get(key)))
    for loc in _as_list(record.get("locations")):
        if isinstance(loc, dict):
            parts = [
                loc.get("address"), loc.get("street"), loc.get("city"),
                loc.get("state"), loc.get("postal_code") or loc.get("zip"),
            ]
            values.append(" ".join(str(p) for p in parts if p))
    return sorted({a for a in (_normalize_address(str(v)) for v in values) if a})


def identity(record: dict[str, Any]) -> dict[str, Any]:
    name = record.get("name") or record.get("organization_name") or record.get("title") or ""
    alternate_names = [str(v) for v in _as_list(record.get("alternate_names"))]
    names = sorted({_normalize_name(name), *(_normalize_name(v) for v in alternate_names)} - {""})
    phones = _phones(record)
    domains = _domains(record)
    urls = _urls(record)
    addresses = _addresses(record)
    key_source = "|".join([names[0] if names else "", phones[0] if phones else "", domains[0] if domains else "", addresses[0] if addresses else ""])
    digest = hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:16]
    return {
        "name": str(name),
        "normalized_names": names,
        "phones": phones,
        "domains": domains,
        "urls": urls,
        "addresses": addresses,
        "dedup_key": f"{names[0] if names else 'unnamed'}|{phones[0] if phones else domains[0] if domains else digest}",
    }


def _resource_key(record: dict[str, Any]) -> str:
    return identity(record)["dedup_key"]


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------

def empty_dedup() -> dict[str, Any]:
    return {
        "version": 2,
        "processed_zips": {},
        "zip_runs": {},
        "discovered": {},
        "out_of_area": {},
        "stats": {
            "total_discovered": 0,
            "total_new": 0,
            "total_duplicates": 0,
            "total_out_of_area": 0,
            "last_run": None,
        },
    }


def load_dedup() -> dict[str, Any]:
    dedup = load_json(DEDUP_PATH, empty_dedup())
    baseline = empty_dedup()
    for key, value in baseline.items():
        dedup.setdefault(key, value)
    dedup["version"] = max(int(dedup.get("version", 1)), 2)
    return dedup


def save_dedup(dedup: dict[str, Any]) -> None:
    write_json(DEDUP_PATH, dedup)


def load_existing_resources() -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    main = DATA_DIR / "resources.json"
    if main.exists():
        data = load_json(main, {})
        resources.extend(r for r in data.get("resources", []) if isinstance(r, dict))
    for state_dir in (DATA_DIR / "states").iterdir() if (DATA_DIR / "states").exists() else []:
        sr = state_dir / "resources.json"
        if sr.exists():
            data = load_json(sr, {})
            resources.extend(r for r in data.get("resources", []) if isinstance(r, dict))
    approved = SOURCE_DIR / "approved"
    if approved.exists():
        try:
            import yaml  # type: ignore
        except ImportError:
            yaml = None
        if yaml is not None:
            for path in sorted(approved.rglob("*.yaml")):
                loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    loaded.setdefault("_source_path", str(path.relative_to(BEACON_ROOT)))
                    resources.append(loaded)
    return resources


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if not CASES_DIR.exists():
        return cases
    for path in sorted(CASES_DIR.glob("*.json")):
        case = load_json(path, None)
        if isinstance(case, dict):
            lead = case.get("lead", {}) if isinstance(case.get("lead"), dict) else {}
            record = {
                "name": lead.get("name") or case.get("organization_name") or case.get("name"),
                "phones": [lead.get("proposed_phone")],
                "url": lead.get("proposed_url"),
                "source_url": lead.get("source_url"),
                "address": lead.get("proposed_address"),
                "case_id": case.get("case_id"),
                "state": case.get("state"),
                "_source_path": str(path.relative_to(BEACON_ROOT)),
            }
            cases.append(record)
    return cases


def load_rejected() -> list[dict[str, Any]]:
    rejected: list[dict[str, Any]] = []
    if not REJECTED_DIR.exists():
        return rejected
    for path in sorted(REJECTED_DIR.glob("*.json")):
        item = load_json(path, None)
        if isinstance(item, dict):
            item.setdefault("_source_path", str(path.relative_to(BEACON_ROOT)))
            rejected.append(item)
    return rejected


def load_prior_run_leads() -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    for path in sorted(RUNS_DIR.glob("*/*-processed.json")) if RUNS_DIR.exists() else []:
        run = load_json(path, {})
        for bucket in ("new_leads", "out_of_area", "near_duplicates", "possible_related_programs", "reconsider_rejected"):
            for resource in run.get(bucket, []) or []:
                if isinstance(resource, dict):
                    resource = dict(resource)
                    resource.setdefault("_source_path", str(path.relative_to(BEACON_ROOT)))
                    leads.append(resource)
    for path in sorted(LEADS_DIR.glob("leads_*.json")):
        run = load_json(path, {})
        for bucket in ("new_leads", "out_of_area"):
            for resource in run.get(bucket, []) or []:
                if isinstance(resource, dict):
                    resource = dict(resource)
                    resource.setdefault("_source_path", str(path.relative_to(BEACON_ROOT)))
                    leads.append(resource)
    return leads


def build_exclude_list(existing: list[dict[str, Any]]) -> str:
    names = sorted({str(r.get("name") or r.get("title") or "") for r in existing if r.get("name") or r.get("title")})
    return "\n".join(f"- {n}" for n in names) if names else "(no existing resources to exclude)"


# ---------------------------------------------------------------------------
# Duplicate classification
# ---------------------------------------------------------------------------

def _overlap(a: list[str], b: list[str]) -> list[str]:
    return sorted(set(a) & set(b))


def _name_overlap(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    return _overlap(a["normalized_names"], b["normalized_names"])


def _first_source(record: dict[str, Any]) -> str:
    return str(record.get("_source_path") or record.get("source_run_id") or record.get("case_id") or record.get("dedup_key") or "unknown")


def _match(candidate: dict[str, Any], existing: dict[str, Any]) -> tuple[str, list[str]] | None:
    names = _name_overlap(candidate, existing)
    phones = _overlap(candidate["phones"], existing["phones"])
    domains = _overlap(candidate["domains"], existing["domains"])
    urls = _overlap(candidate["urls"], existing["urls"])
    addresses = _overlap(candidate["addresses"], existing["addresses"])

    if urls:
        return "same_canonical_url", ["url"]
    if names and phones:
        return "same_name_same_phone", ["normalized_name", "phone"]
    if names and domains:
        return "same_name_same_domain", ["normalized_name", "domain"]
    if phones and addresses:
        return "same_phone_same_address", ["phone", "address"]
    if domains and addresses:
        return "same_domain_same_address", ["domain", "address"]
    if names and addresses:
        return "same_name_same_address", ["normalized_name", "address"]
    if names:
        return "same_name", ["normalized_name"]
    if phones or domains or addresses:
        return "shared_locator", [f for f, v in (("phone", phones), ("domain", domains), ("address", addresses)) if v]
    return None


def _classification(classification: str, source: str, match_type: str, fields: list[str], confidence: str = "high") -> dict[str, Any]:
    return {
        "classification": classification,
        "matched": {
            "source": source,
            "match_type": match_type,
            "matched_fields": fields,
            "confidence": confidence,
        },
    }


def _dedup_record_to_resource(key: str, value: dict[str, Any]) -> dict[str, Any]:
    resource = dict(value)
    resource.setdefault("name", value.get("name", ""))
    resource.setdefault("phones", value.get("phones", []))
    resource.setdefault("url", value.get("url"))
    resource.setdefault("address", value.get("address"))
    resource.setdefault("dedup_key", key)
    resource.setdefault("_source_path", f"leads/dedup.json:{key}")
    return resource


def _minimum_locator(resource: dict[str, Any], ident: dict[str, Any]) -> bool:
    if not ident["normalized_names"]:
        return False
    if ident["phones"] or ident["domains"] or ident["urls"] or ident["addresses"]:
        return True
    return bool(resource.get("source_url") or resource.get("source_urls"))


def classify_lead(resource: dict[str, Any], indexes: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    cand = identity(resource)
    category = resource.get("category")
    if category and category not in CATEGORIES:
        return _classification("policy_rejected", "lead_generation_policy", "invalid_category", ["category"])
    if not _minimum_locator(resource, cand):
        return _classification("insufficient_info", "lead_generation_policy", "missing_locator", ["name", "locator"], "high")

    for source, classification in (
        ("published", "duplicate_existing_resource"),
        ("cases", "duplicate_existing_case"),
    ):
        for item in indexes[source]:
            match = _match(cand, identity(item))
            if not match:
                continue
            match_type, fields = match
            if match_type == "shared_locator":
                return _classification("possible_related_program", _first_source(item), match_type, fields, "medium")
            if match_type == "same_name":
                return _classification("near_duplicate_review", _first_source(item), match_type, fields, "medium")
            return _classification(classification, _first_source(item), match_type, fields)

    for item in indexes["dedup"]:
        match = _match(cand, identity(item))
        if not match:
            continue
        match_type, fields = match
        status = item.get("status")
        if status == "rejected":
            if resource.get("source_url") and resource.get("source_url") != item.get("source_url"):
                return _classification("reconsider_rejected", _first_source(item), match_type, fields, "medium")
            return _classification("previously_rejected", _first_source(item), match_type, fields)
        if match_type in {"same_name", "shared_locator"}:
            return _classification("near_duplicate_review", _first_source(item), match_type, fields, "medium")
        return _classification("duplicate_existing_lead", _first_source(item), match_type, fields)

    for item in indexes["prior_runs"]:
        match = _match(cand, identity(item))
        if not match:
            continue
        match_type, fields = match
        if match_type in {"same_name", "shared_locator"}:
            return _classification("near_duplicate_review", _first_source(item), match_type, fields, "medium")
        return _classification("duplicate_prior_run", _first_source(item), match_type, fields)

    for item in indexes["rejected"]:
        match = _match(cand, identity(item))
        if not match:
            continue
        match_type, fields = match
        if resource.get("source_url") and resource.get("source_url") != item.get("source_url"):
            return _classification("reconsider_rejected", _first_source(item), match_type, fields, "medium")
        return _classification("previously_rejected", _first_source(item), match_type, fields)

    return {"classification": "new", "matched": None}


def build_indexes() -> dict[str, list[dict[str, Any]]]:
    dedup = load_dedup()
    dedup_records = [
        _dedup_record_to_resource(key, value)
        for key, value in dedup.get("discovered", {}).items()
        if isinstance(value, dict)
    ]
    return {
        "published": load_existing_resources(),
        "cases": load_cases(),
        "dedup": dedup_records,
        "prior_runs": load_prior_run_leads(),
        "rejected": load_rejected(),
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def render_prompt(zip_code: str) -> dict[str, Any]:
    info = resolve_zip(zip_code)
    area = f"{info['county']} County, {info['state']}" if info["county"] != "Unknown" else f"ZIP {zip_code}"
    existing = load_existing_resources() + load_cases() + [
        _dedup_record_to_resource(k, v)
        for k, v in load_dedup().get("discovered", {}).items()
        if isinstance(v, dict)
    ]
    exclude = build_exclude_list(existing)
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("$area_description", area)
        .replace("$zip", info["zip"])
        .replace("$county", info["county"])
        .replace("$state", info["state"])
        .replace("$exclude_list", exclude)
    )
    return {
        "zip": info["zip"],
        "county": info["county"],
        "state": info["state"],
        "city": info.get("city", ""),
        "area_description": area,
        "prompt": prompt,
        "categories": CATEGORIES,
        "existing_resource_count": len(load_existing_resources()),
        "existing_case_count": len(load_cases()),
        "existing_lead_count": len(load_dedup().get("discovered", {})),
        "guidance": "Run research, save JSON with resources_found, then run: python3 leads/research.py process <zip> <results.json>",
    }


def cmd_prompt(args: list[str]) -> None:
    if len(args) < 1:
        print("Usage: research.py prompt <zip>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(render_prompt(args[0]), indent=2, ensure_ascii=False))


def cmd_plan(args: list[str]) -> None:
    if len(args) < 1:
        print("Usage: research.py plan <zip>", file=sys.stderr)
        sys.exit(1)
    zip_code = re.sub(r"\D", "", args[0]).zfill(5)
    run_id = make_run_id(zip_code)
    prompt_payload = render_prompt(zip_code)
    run_dir = RUNS_DIR / zip_code
    manifest = {
        "run_id": run_id,
        "zip": zip_code,
        "county": prompt_payload["county"],
        "state": prompt_payload["state"],
        "city": prompt_payload["city"],
        "started_at": utc_now(),
        "status": "planned",
        "mode": "initial" if not load_dedup().get("zip_runs", {}).get(zip_code) else "rerun",
        "categories_planned": CATEGORIES,
        "prompt_file": str((run_dir / f"{run_id}-prompt.json").relative_to(BEACON_ROOT)),
    }
    write_json(run_dir / f"{run_id}-manifest.json", manifest)
    write_json(run_dir / f"{run_id}-prompt.json", prompt_payload)
    print(json.dumps({"ok": True, **manifest}, indent=2))


def cmd_process(args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: research.py process <zip> <results.json> [--dry-run]", file=sys.stderr)
        sys.exit(1)
    dry_run = "--dry-run" in args
    filtered = [arg for arg in args if arg != "--dry-run"]
    zip_code = re.sub(r"\D", "", filtered[0]).zfill(5)
    results_path = Path(filtered[1])
    if not results_path.exists():
        print(f"Results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    results = load_json(results_path, {})
    info = resolve_zip(zip_code)
    run_id = make_run_id(zip_code)
    now = utc_now()
    indexes = build_indexes()
    dedup = load_dedup()

    buckets: dict[str, list[dict[str, Any]]] = {
        "new_leads": [],
        "duplicates": [],
        "near_duplicates": [],
        "possible_related_programs": [],
        "out_of_area": [],
        "insufficient_info": [],
        "rejected": [],
        "reconsider_rejected": [],
    }

    resources = results.get("resources_found", [])
    if not isinstance(resources, list):
        print("results.json must contain resources_found array", file=sys.stderr)
        sys.exit(1)

    for resource in resources:
        if not isinstance(resource, dict):
            continue
        resource = dict(resource)
        resource.setdefault("found_in_zip", zip_code)
        resource.setdefault("first_seen", now)
        resource["dedup_key"] = _resource_key(resource)
        resource["source_run_id"] = run_id
        decision = classify_lead(resource, indexes)
        classification = decision["classification"]
        resource["classification"] = classification
        resource["matched"] = decision.get("matched")

        found_zip = str(resource.get("found_outside_zip") or "").strip()
        if classification == "new" and found_zip and found_zip != zip_code:
            classification = "out_of_area_new"
            resource["classification"] = classification

        if classification == "new":
            buckets["new_leads"].append(resource)
            indexes["dedup"].append(resource)
        elif classification == "out_of_area_new":
            buckets["out_of_area"].append(resource)
            indexes["dedup"].append(resource)
        elif classification in {"near_duplicate_review"}:
            buckets["near_duplicates"].append(resource)
        elif classification == "possible_related_program":
            buckets["possible_related_programs"].append(resource)
        elif classification == "reconsider_rejected":
            buckets["reconsider_rejected"].append(resource)
        elif classification == "insufficient_info":
            buckets["insufficient_info"].append(resource)
        elif classification in {"previously_rejected", "policy_rejected"}:
            buckets["rejected"].append(resource)
        else:
            buckets["duplicates"].append(resource)

    if not dry_run:
        for lead in buckets["new_leads"] + buckets["out_of_area"]:
            key = lead["dedup_key"]
            existing = dedup["discovered"].get(key, {}) if isinstance(dedup["discovered"].get(key), dict) else {}
            dedup["discovered"][key] = {
                "name": lead.get("name", ""),
                "normalized_names": identity(lead)["normalized_names"],
                "phones": identity(lead)["phones"],
                "domains": identity(lead)["domains"],
                "urls": identity(lead)["urls"],
                "addresses": identity(lead)["addresses"],
                "zip": lead.get("found_in_zip", zip_code),
                "located_zip": lead.get("found_outside_zip") or lead.get("zip"),
                "county": info["county"],
                "state": info["state"],
                "status": "queued",
                "first_seen": existing.get("first_seen", lead.get("first_seen", now)),
                "last_seen": now,
                "times_seen": int(existing.get("times_seen", 0)) + 1,
                "source_run_ids": sorted(set(existing.get("source_run_ids", []) + [run_id])),
                "source_url": lead.get("source_url") or (lead.get("source_urls") or [None])[0],
            }
        for ooa in buckets["out_of_area"]:
            dedup["out_of_area"][ooa["dedup_key"]] = {
                "name": ooa.get("name", ""),
                "serves_zip": zip_code,
                "located_zip": ooa.get("found_outside_zip", "unknown"),
                "county": info["county"],
                "first_seen": ooa.get("first_seen", now),
                "source_run_id": run_id,
            }

        dedup.setdefault("zip_runs", {}).setdefault(zip_code, []).append(run_id)
        dedup["processed_zips"][zip_code] = {
            "county": info["county"],
            "state": info["state"],
            "processed_at": now,
            "latest_run_id": run_id,
            "resources_found": len(resources),
            "new_leads": len(buckets["new_leads"]),
            "duplicates": len(buckets["duplicates"]),
            "near_duplicates": len(buckets["near_duplicates"]),
            "out_of_area": len(buckets["out_of_area"]),
        }
        dedup["stats"]["total_discovered"] = len(dedup.get("discovered", {}))
        dedup["stats"]["total_new"] = dedup["stats"].get("total_new", 0) + len(buckets["new_leads"])
        dedup["stats"]["total_duplicates"] = dedup["stats"].get("total_duplicates", 0) + len(buckets["duplicates"])
        dedup["stats"]["total_out_of_area"] = len(dedup.get("out_of_area", {}))
        dedup["stats"]["last_run"] = now
        save_dedup(dedup)

    processed = {
        "run_id": run_id,
        "zip": zip_code,
        "county": info["county"],
        "state": info["state"],
        "processed_at": now,
        "dry_run": dry_run,
        **buckets,
        "summary": {
            "total_found": len(resources),
            "new": len(buckets["new_leads"]),
            "duplicates": len(buckets["duplicates"]),
            "near_duplicates": len(buckets["near_duplicates"]),
            "possible_related_programs": len(buckets["possible_related_programs"]),
            "out_of_area": len(buckets["out_of_area"]),
            "insufficient_info": len(buckets["insufficient_info"]),
            "rejected": len(buckets["rejected"]),
            "reconsider_rejected": len(buckets["reconsider_rejected"]),
        },
    }

    run_dir = RUNS_DIR / zip_code
    processed_path = run_dir / f"{run_id}-processed.json"
    raw_path = run_dir / f"{run_id}-raw.json"
    legacy_path = LEADS_DIR / f"leads_{zip_code}_{run_id}.json"
    if not dry_run:
        run_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(results_path, raw_path)
        write_json(processed_path, processed)
        write_json(legacy_path, processed)

    summary = {
        "ok": True,
        "dry_run": dry_run,
        "zip": zip_code,
        "county": info["county"],
        "state": info["state"],
        "run_id": run_id,
        **processed["summary"],
        "processed_file": None if dry_run else str(processed_path.relative_to(BEACON_ROOT)),
        "legacy_file": None if dry_run else str(legacy_path.relative_to(BEACON_ROOT)),
        "dedup_total": len(dedup.get("discovered", {})),
        "next": "review processed leads and promote exactly one lead to a pilot case",
    }
    print(json.dumps(summary, indent=2))


def cmd_status(args: list[str]) -> None:
    dedup = load_dedup()
    zips = dedup.get("processed_zips", {})
    stats = dedup.get("stats", {})
    summary = {
        "processed_zips": len(zips),
        "zip_list": sorted(zips.keys()),
        "zip_runs": {k: len(v) for k, v in sorted(dedup.get("zip_runs", {}).items())},
        "total_discovered": stats.get("total_discovered", 0),
        "total_new": stats.get("total_new", 0),
        "total_duplicates": stats.get("total_duplicates", 0),
        "total_out_of_area": stats.get("total_out_of_area", 0),
        "last_run": stats.get("last_run"),
    }
    print(json.dumps(summary, indent=2))


def cmd_leads(args: list[str]) -> None:
    dedup = load_dedup()
    discovered = dedup.get("discovered", {})
    leads = [
        {
            "key": k,
            "name": v.get("name", ""),
            "zip": v.get("zip", ""),
            "county": v.get("county", ""),
            "status": v.get("status", ""),
            "first_seen": v.get("first_seen", ""),
            "last_seen": v.get("last_seen", ""),
            "times_seen": v.get("times_seen", 1),
        }
        for k, v in sorted(discovered.items(), key=lambda x: x[1].get("name", ""))
        if isinstance(v, dict)
    ]
    print(json.dumps({"total": len(leads), "leads": leads}, indent=2))


def cmd_out_of_area(args: list[str]) -> None:
    dedup = load_dedup()
    ooa = dedup.get("out_of_area", {})
    resources = [
        {
            "key": k,
            "name": v.get("name", ""),
            "serves_zip": v.get("serves_zip", ""),
            "located_zip": v.get("located_zip", ""),
            "county": v.get("county", ""),
        }
        for k, v in sorted(ooa.items(), key=lambda x: x[1].get("name", ""))
        if isinstance(v, dict)
    ]
    print(json.dumps({"total": len(resources), "resources": resources}, indent=2))


def cmd_needs(args: list[str]) -> None:
    if len(args) < 1:
        print("Usage: research.py needs <zip|state_abbr>", file=sys.stderr)
        sys.exit(1)
    target = args[0].strip()
    census_path = DATA_DIR / "census" / "us-zips-census.json"
    if not census_path.exists():
        print(json.dumps({"error": "Census indicators not found. Run data/census/census_indicators.py first."}))
        sys.exit(1)
    census_data = load_json(census_path, {})
    needs_path = DATA_DIR / "census" / "needs-analysis.json"
    needs_data = load_json(needs_path, {})
    existing = load_existing_resources()
    zip_counts: dict[str, int] = {}
    for r in existing:
        locs = r.get("locations", [])
        if locs:
            for loc in locs:
                if isinstance(loc, dict):
                    zc = (loc.get("postal_code") or loc.get("zip", "")).strip().zfill(5)
                    if zc:
                        zip_counts[zc] = zip_counts.get(zc, 0) + 1
        else:
            zc = (r.get("zip", "") or r.get("postal_code", "")).strip().zfill(5)
            if zc:
                zip_counts[zc] = zip_counts.get(zc, 0) + 1

    if len(target) == 2 and target.isalpha():
        state = target.upper()
        state_summary = needs_data.get("state_summaries", {}).get(state)
        state_zips = {z: d for z, d in needs_data.get("zip_analysis", {}).items() if d.get("state") == state}
        total_resources = sum(1 for z in state_zips if zip_counts.get(z, 0) > 0)
        output = {
            "type": "state",
            "state": state,
            "summary": state_summary,
            "resource_coverage": {"zips_with_resources": total_resources, "total_zips": len(state_zips)},
            "high_need_zips_sample": [
                {"zip": z, "need_score": d.get("need_score"), "poverty_rate": d.get("poverty_rate"),
                 "snap_rate": d.get("snap_rate"), "existing_resources": zip_counts.get(z, 0)}
                for z, d in sorted(state_zips.items(), key=lambda x: x[1].get("need_score") or 0, reverse=True)
                if d.get("need_flag") == "high"
            ][:20],
        }
        print(json.dumps(output, indent=2))
        return

    zc = target.zfill(5)
    indicators = census_data.get(zc, {})
    needs = needs_data.get("zip_analysis", {}).get(zc, {})
    info = resolve_zip(zc)
    county = info.get("county", "Unknown")
    state = info.get("state", "Unknown")
    county_zips = {z: d for z, d in needs_data.get("zip_analysis", {}).items() if d.get("county") == county and d.get("state") == state}
    county_resources = sum(zip_counts.get(z, 0) for z in county_zips)
    output = {
        "zip": zc,
        "county": county,
        "state": state,
        "city": info.get("city", ""),
        "census_indicators": indicators,
        "needs_score": needs.get("need_score"),
        "need_flag": needs.get("need_flag"),
        "existing_resources": zip_counts.get(zc, 0),
        "county_context": {
            "total_zips": len(county_zips),
            "county_total_resources": county_resources,
            "avg_poverty": round(sum(d.get("poverty_rate", 0) or 0 for d in county_zips.values()) / max(len(county_zips), 1), 1),
            "avg_snap": round(sum(d.get("snap_rate", 0) or 0 for d in county_zips.values()) / max(len(county_zips), 1), 1),
        },
    }
    print(json.dumps(output, indent=2))


COMMANDS = {
    "prompt": cmd_prompt,
    "plan": cmd_plan,
    "process": cmd_process,
    "status": cmd_status,
    "leads": cmd_leads,
    "out-of-area": cmd_out_of_area,
    "needs": cmd_needs,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: research.py <{'|'.join(COMMANDS.keys())}> [args...]", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print("  prompt <zip>                         Generate search prompt", file=sys.stderr)
        print("  plan <zip>                           Create lead-generation run manifest", file=sys.stderr)
        print("  process <zip> <results.json> [--dry-run]  Dedup and save findings", file=sys.stderr)
        print("  status                               Show processing status", file=sys.stderr)
        print("  leads                                List all discovered leads", file=sys.stderr)
        print("  out-of-area                          List out-of-area resources", file=sys.stderr)
        print("  needs <zip|state>                    Show Census needs indicators", file=sys.stderr)
        sys.exit(2)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
