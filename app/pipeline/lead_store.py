"""LeadStore — inline dedup and validation for the research agent.

Wraps the existing research.py dedup logic into a tool-callable interface.
Every create_lead() call is validated and deduped in real time — the agent
gets immediate feedback rather than discovering duplicates in post-processing.

Also manages seen_urls so repeat runs on the same ZIP skip already-evaluated
URLs and only surface genuinely new resources.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BEACON_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BEACON_ROOT / "leads"))
sys.path.insert(0, str(BEACON_ROOT / "scripts"))

import research as _r           # leads/research.py
import seen_urls as _su         # leads/seen_urls.py

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation constants (mirrors resource.schema.json enums)
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    "food", "shelter", "housing", "health", "mental-health", "addiction",
    "crisis", "family", "legal", "documents", "education", "jobs",
    "transportation", "utility-assistance", "clothing", "community", "veterans",
}

VALID_POPULATIONS = {
    "anyone", "families", "women", "men", "youth", "seniors", "veterans",
    "lgbtq+", "disability", "re-entry", "pregnant", "substance-use", "recovery",
}

VALID_SERVICE_TYPES = {
    "hotline", "walk-in", "appointment", "residential", "outpatient",
    "mobile", "online", "peer-led", "faith-based", "government",
}

VALID_COSTS = {"free", "sliding-scale", "insurance", "unknown"}

SENSITIVE_CATEGORIES = {"crisis"}  # require extra care; flag but don't block


# ---------------------------------------------------------------------------
# LeadStore
# ---------------------------------------------------------------------------

class LeadStore:
    """Stateful store for one research run.

    Maintains:
      - indexes: published resources + candidates + dedup dict + prior leads
      - seen_urls registry: URLs already evaluated (persists across runs)
      - session_leads: leads saved so far in this run (for in-session dedup)

    Call finalize() at the end of the run to write all session leads to the
    run artifact file and call research.py process for bookkeeping.
    """

    def __init__(self, zip_code: str, zip_info: dict):
        self.zip_code = zip_code
        self.zip_info = zip_info
        self.run_id = _r.make_run_id(zip_code)
        self.started_at = _utc_now()

        # Load dedup indexes from all existing sources
        self._indexes = _r.build_indexes()

        # Session-level leads saved so far (for within-run dedup)
        self.session_leads: list[dict] = []
        # Index of session leads for fast dedup
        self._session_index: list[dict] = []

        # Seen-URL registry (persists between runs)
        self._seen_urls: dict[str, dict] = _su.load()

        log.info(
            "LeadStore ready — %d published, %d cases, %d dedup, %d seen_urls",
            len(self._indexes["published"]),
            len(self._indexes["cases"]),
            len(self._indexes["dedup"]),
            len(self._seen_urls),
        )

    # ------------------------------------------------------------------
    # Public context summary (for system prompt)
    # ------------------------------------------------------------------

    def context_summary(self) -> dict:
        """Counts the agent needs to know up front."""
        return {
            "published_resources": len(self._indexes["published"]),
            "in_progress_candidates": len(self._indexes["cases"]),
            "known_leads": len(self._indexes["dedup"]),
            "seen_urls": len(self._seen_urls),
            "session_leads_so_far": len(self.session_leads),
        }

    # ------------------------------------------------------------------
    # Tool: create_lead
    # ------------------------------------------------------------------

    async def handle_create_lead(self, args: dict) -> str:
        result = self._create_lead(args)
        return json.dumps(result, indent=2)

    def _create_lead(self, args: dict) -> dict:
        # 1. Validate required fields
        errors = _validate_lead(args)
        if errors:
            return {
                "status": "error",
                "errors": errors,
                "hint": "Fix the errors above and try again. source_urls is required evidence.",
            }

        # 2. Normalize
        lead = _normalize_lead(args, self.zip_code, self.zip_info)

        # 3a. Hard dedup — conclusive signals only (same physical location, etc.)
        hard = self._find_hard_duplicate(lead)
        if hard:
            log.info("hard-duplicate: %s → %s (blocked)", lead["name"], hard["match_type"])
            return {
                "status": "duplicate",
                "name": lead["name"],
                "match_type": hard["match_type"],
                "matched_fields": hard["matched_fields"],
                "matched_name": hard.get("matched_name", ""),
                "source": hard["source"],
                "hint": "Same physical location / same org contact — definitely a duplicate. Move on.",
            }

        # 3b. Soft dedup — suspicious but not conclusive → save + flag for AI review
        soft = self._find_soft_duplicate(lead)
        review_flag = None
        if soft:
            log.info("soft-flag: %s → possible dup of '%s' (%s) — saving for AI review",
                     lead["name"], soft["matched_name"], soft["match_type"])
            review_flag = soft

        # 4. Flag sensitive categories (don't block, but note it)
        flags = []
        if lead.get("category") in SENSITIVE_CATEGORIES:
            flags.append(f"Sensitive category '{lead['category']}' — requires extra verification before promotion")

        # 5. Save to session (always — hard dups are already blocked above)
        lead["session_run_id"] = self.run_id
        lead["found_at"] = _utc_now()
        if review_flag:
            lead["review_flag"] = review_flag   # picked up by research.py process
        self.session_leads.append(lead)
        # Add to in-session index immediately so next call can hard-match against it
        self._session_index.append(lead)

        # 6. Mark source_urls as seen
        for url in lead.get("source_urls", []):
            if url and url not in self._seen_urls:
                self._seen_urls[url] = {
                    "outcome": "new_lead",
                    "name": lead["name"],
                    "run_id": self.run_id,
                    "zip": self.zip_code,
                }

        lead_id = f"{self.run_id}-{len(self.session_leads):03d}"
        log.info("saved lead #%d: %s", len(self.session_leads), lead["name"])

        # Checkpoint every 10 leads — work survives timeouts and crashes
        if len(self.session_leads) % 10 == 0:
            self._checkpoint()

        review_info = {}
        if review_flag:
            flags.append(
                f"Possible duplicate of '{review_flag['matched_name']}' "
                f"({review_flag['match_type']}) — saved for AI review. "
                "If you believe these are the same org, skip further research on it. "
                "If clearly different, ignore this flag."
            )
            review_info = {
                "possible_duplicate_of": review_flag["matched_name"],
                "match_type": review_flag["match_type"],
                "match_source": review_flag["source"],
            }

        return {
            "status": "saved",
            "id": lead_id,
            "name": lead["name"],
            "category": lead["category"],
            "located_zip": lead.get("zip"),
            "out_of_area": lead.get("zip") != self.zip_code,
            "session_total": len(self.session_leads),
            "flags": flags,
            **review_info,
        }

    # ------------------------------------------------------------------
    # Tool: check_url
    # ------------------------------------------------------------------

    async def handle_check_url(self, args: dict) -> str:
        url = args.get("url", "").strip()
        if not url:
            return json.dumps({"error": "url is required"})

        entry = self._seen_urls.get(url)
        if entry:
            return json.dumps({
                "seen": True,
                "outcome": entry["outcome"],
                "name": entry.get("name", ""),
                "run_id": entry.get("run_id", ""),
                "hint": (
                    "Already processed. "
                    + ("This URL produced a lead — skip it." if entry["outcome"] == "new_lead"
                       else "This URL was visited and produced no new lead.")
                ),
            })

        return json.dumps({"seen": False, "hint": "URL not previously evaluated — safe to visit."})

    # ------------------------------------------------------------------
    # Checkpoint: persist work-in-progress so crashes don't lose leads
    # ------------------------------------------------------------------

    def _checkpoint(self) -> None:
        """Write current session leads to disk. Called every 10 leads and at finalize."""
        if not self.session_leads:
            return
        run_dir = BEACON_ROOT / "leads" / "runs" / self.zip_code
        run_dir.mkdir(parents=True, exist_ok=True)
        ckpt = run_dir / f"{self.run_id}-checkpoint.json"
        ckpt.write_text(json.dumps({
            "zip": self.zip_code,
            "county": self.zip_info["county"],
            "state": self.zip_info["state"],
            "run_id": self.run_id,
            "checkpoint_at": _utc_now(),
            "lead_count": len(self.session_leads),
            "resources_found": self.session_leads,
        }, indent=2, ensure_ascii=False))
        _su.save(self._seen_urls)
        log.debug("checkpoint: %d leads saved to %s", len(self.session_leads), ckpt.name)

    # ------------------------------------------------------------------
    # Finalize: save session leads and update bookkeeping
    # ------------------------------------------------------------------

    def finalize(self) -> dict:
        """Write run artifact and update dedup.json + seen_urls.json.

        Safe to call even if the agent was interrupted — checkpoint() has been
        writing incrementally every 10 leads. finalize() promotes the checkpoint
        to a permanent processed run file.
        """
        self._checkpoint()  # ensure latest state is on disk regardless

        if not self.session_leads:
            log.info("finalize: no new leads this session")
            return {"new_leads": 0, "run_id": self.run_id}

        # Write raw results in the format research.py process expects
        raw = {
            "zip": self.zip_code,
            "county": self.zip_info["county"],
            "state": self.zip_info["state"],
            "resources_found": self.session_leads,
        }
        run_dir = BEACON_ROOT / "leads" / "runs" / self.zip_code
        run_dir.mkdir(parents=True, exist_ok=True)
        raw_path = run_dir / f"{self.run_id}-raw.json"
        raw_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False))

        # Call research.py process (handles dedup.json update + classification)
        import subprocess
        result = subprocess.run(
            [sys.executable, str(BEACON_ROOT / "leads" / "research.py"),
             "process", self.zip_code, str(raw_path)],
            capture_output=True, text=True, cwd=str(BEACON_ROOT),
        )
        if result.returncode != 0:
            log.error("research.py process failed: %s", result.stderr)
        else:
            try:
                summary = json.loads(result.stdout)
                log.info("process summary: %s", summary.get("summary", {}))
            except json.JSONDecodeError:
                log.warning("process output not JSON: %s", result.stdout[:200])

        # Persist seen_urls
        _su.save(self._seen_urls)
        log.info("finalize: saved %d leads, updated seen_urls (%d total)",
                 len(self.session_leads), len(self._seen_urls))

        return {
            "run_id": self.run_id,
            "new_leads": len(self.session_leads),
            "raw_file": str(raw_path.relative_to(BEACON_ROOT)),
        }

    # ------------------------------------------------------------------
    # Internal dedup
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Dedup — hard block vs. soft flag
    # ------------------------------------------------------------------
    # Philosophy: deterministic rules are good at finding SUSPICIOUS pairs,
    # not at deciding if two records are truly the same org.  We hard-block
    # only when the signal is logically conclusive (same physical location,
    # same org name+phone).  Everything else is a soft flag — the lead is
    # saved but marked for AI review.
    #
    # HARD BLOCK (match_type):
    #   same_phone_same_address  — identical physical location
    #   same_name_same_phone     — same org name + same contact number
    #   same_name_same_address   — same org name + same physical address
    #   same_domain_same_address — same website + same building
    #
    # SOFT FLAG (everything else, including same_canonical_url, same_name,
    #   shared_locator, same_name_same_domain) — save the lead, attach
    #   review_flag, let AI decide later.
    # ------------------------------------------------------------------

    _HARD_MATCH_TYPES = frozenset({
        "same_phone_same_address",
        "same_name_same_phone",
        "same_name_same_address",
        "same_domain_same_address",
    })

    @staticmethod
    def _id(r: dict) -> dict:
        """Identity stripped of source_urls — discovery evidence, not org identity."""
        stripped = {k: v for k, v in r.items()
                    if k not in ("source_urls", "source_url")}
        return _r.identity(stripped)

    def _scan_indexes(self, lead: dict) -> dict | None:
        """Return first match across all indexes, or None."""
        cand = self._id(lead)
        source_map = [
            ("published",    self._indexes["published"]),
            ("candidates",   self._indexes["cases"]),
            ("prior_leads",  self._indexes["dedup"]),
            ("rejected",     self._indexes["rejected"]),
            ("this_session", self._session_index),
        ]
        for source_name, items in source_map:
            for existing in items:
                m = _r._match(cand, self._id(existing))
                if m:
                    match_type, fields = m
                    return {
                        "source": source_name,
                        "match_type": match_type,
                        "matched_fields": fields,
                        "matched_name": existing.get("name", ""),
                    }
        return None

    def _find_hard_duplicate(self, lead: dict) -> dict | None:
        """Hard block: conclusive signals only. Returns match or None."""
        match = self._scan_indexes(lead)
        if match and match["match_type"] in self._HARD_MATCH_TYPES:
            return match
        return None

    def _find_soft_duplicate(self, lead: dict) -> dict | None:
        """Soft flag: suspicious but not conclusive. Returns match or None."""
        match = self._scan_indexes(lead)
        if match and match["match_type"] not in self._HARD_MATCH_TYPES:
            return match
        return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_lead(args: dict) -> list[str]:
    errors = []

    name = (args.get("name") or "").strip()
    if not name:
        errors.append("name is required")

    category = args.get("category", "")
    if category not in VALID_CATEGORIES:
        errors.append(
            f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}. "
            f"Got: {category!r}"
        )

    # Minimum locator: need at least one of phone, url, address
    has_phone   = bool((args.get("phones") or [args.get("phone")]) and
                       any(args.get("phones") or [args.get("phone")]))
    has_url     = bool(args.get("url", "").strip())
    has_address = bool(args.get("address", "").strip())
    if not (has_phone or has_url or has_address):
        errors.append(
            "At least one of 'phone', 'url', or 'address' is required. "
            "Do not save a lead with only a name."
        )

    # Physical locator: non-hotline leads must have address OR phone.
    # A URL-only lead (e.g. saved from an aggregator page without visiting the
    # org's site) is too incomplete — it may reference the wrong org or be
    # hallucinated. Hotlines and websites are exempt if they ARE the service.
    is_hotline = "hotline" in (args.get("service_types") or [])
    is_website_service = category in ("community", "documents") and has_url and not has_address
    if has_url and not has_phone and not has_address and not is_hotline and not is_website_service:
        errors.append(
            "Non-hotline leads require a phone number OR a physical address, not just a URL. "
            "Navigate to the org's own website to find a phone number or address before saving."
        )

    # source_urls: evidence trail
    source_urls = args.get("source_urls") or []
    if not source_urls:
        errors.append(
            "source_urls is required — provide at least one URL where you found this resource. "
            "This is the evidence trail."
        )

    # Optional field validation
    for pop in (args.get("populations") or []):
        if pop not in VALID_POPULATIONS:
            errors.append(f"Unknown population: {pop!r}. Valid: {', '.join(sorted(VALID_POPULATIONS))}")

    for st in (args.get("service_types") or []):
        if st not in VALID_SERVICE_TYPES:
            errors.append(f"Unknown service_type: {st!r}. Valid: {', '.join(sorted(VALID_SERVICE_TYPES))}")

    if args.get("cost") and args["cost"] not in VALID_COSTS:
        errors.append(f"cost must be one of: {', '.join(VALID_COSTS)}")

    return errors


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _normalize_lead(args: dict, zip_code: str, zip_info: dict) -> dict:
    """Produce a clean, consistently structured lead dict."""
    phones = args.get("phones") or ([args["phone"]] if args.get("phone") else [])
    phones = [_r._normalize_phone(p) for p in phones if p]
    phones = [p for p in phones if p]

    source_urls = args.get("source_urls") or []
    url = (args.get("url") or "").strip() or None

    return {
        "name":          args["name"].strip(),
        "category":      args["category"],
        "description":   (args.get("description") or "").strip() or None,
        "phones":        phones,
        "url":           url,
        "address":       (args.get("address") or "").strip() or None,
        "city":          (args.get("city") or zip_info.get("city", "")).strip() or None,
        "county":        (args.get("county") or zip_info["county"]).strip(),
        "state":         (args.get("state") or zip_info["state"]).strip(),
        "zip":           (args.get("zip") or zip_code).strip(),
        "hours":         (args.get("hours") or "").strip() or None,
        "eligibility":   (args.get("eligibility") or "").strip() or None,
        "cost":          args.get("cost") or "unknown",
        "populations":   args.get("populations") or [],
        "service_types": args.get("service_types") or [],
        "source_urls":   source_urls,
        "notes":         (args.get("notes") or "").strip() or None,
        "verification_status": "unverified",
        "confidence":    "medium",
        "found_in_zip":  zip_code,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
