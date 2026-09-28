"""Wayback Machine integration — Save Page Now (SPN2) + availability check.

Two operations:
  wayback_check(url)  → returns closest existing snapshot URL (or None)
  wayback_save(url)   → submits to SPN2, polls until done, returns snapshot URL

Both return a WaybackResult with snapshot_url, timestamp, and status so callers
can store the archived_snapshot value needed for retrieval_integrity scoring.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

log = logging.getLogger(__name__)

_CHECK_URL  = "https://archive.org/wayback/available"
_SAVE_URL   = "https://web.archive.org/save"
_STATUS_URL = "https://web.archive.org/save/status/{job_id}"

_HTTP_TIMEOUT  = 20
_POLL_INTERVAL = 5     # seconds between SPN2 status polls
_POLL_MAX      = 60    # maximum seconds to wait for SPN2 to finish
_FRESH_DAYS    = 30    # existing snapshot counts as "fresh" within this many days


@dataclass
class WaybackResult:
    url: str                        # original URL
    snapshot_url: Optional[str]     # https://web.archive.org/web/TIMESTAMP/URL
    timestamp: Optional[str]        # YYYYMMDDHHmmss
    status: str                     # "found" | "saved" | "pending" | "error" | "none"
    error: Optional[str] = None

    @property
    def archived(self) -> bool:
        return self.snapshot_url is not None

    def as_dict(self) -> dict:
        return {
            "snapshot_url": self.snapshot_url,
            "timestamp": self.timestamp,
            "status": self.status,
            **({"error": self.error} if self.error else {}),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def wayback_check(url: str, max_age_days: int = _FRESH_DAYS) -> WaybackResult:
    """Check Wayback availability API for a recent snapshot.

    If a snapshot younger than max_age_days exists, returns it.
    Otherwise returns WaybackResult(status="none").
    """
    try:
        r = requests.get(
            _CHECK_URL,
            params={"url": url},
            timeout=_HTTP_TIMEOUT,
            headers={"User-Agent": "BeaconDirectoryBot/1.0"},
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("wayback_check failed for %s: %s", url, exc)
        return WaybackResult(url=url, snapshot_url=None, timestamp=None,
                             status="error", error=str(exc))

    closest = data.get("archived_snapshots", {}).get("closest", {})
    if not closest or closest.get("available") is False:
        return WaybackResult(url=url, snapshot_url=None, timestamp=None, status="none")

    ts = closest.get("timestamp", "")
    snap = closest.get("url", "")

    # Check freshness — timestamp is YYYYMMDDHHmmss
    if ts and len(ts) >= 8:
        try:
            import datetime
            snap_date = datetime.datetime.strptime(ts[:8], "%Y%m%d").date()
            age_days = (datetime.date.today() - snap_date).days
            if age_days > max_age_days:
                log.debug("wayback snapshot for %s is %d days old (> %d) — will save fresh",
                          url, age_days, max_age_days)
                return WaybackResult(url=url, snapshot_url=None, timestamp=None, status="stale")
        except ValueError:
            pass

    log.debug("wayback found snapshot for %s: %s", url, snap)
    return WaybackResult(url=url, snapshot_url=snap, timestamp=ts, status="found")


async def wayback_save(url: str, timeout: int = _POLL_MAX) -> WaybackResult:
    """Submit URL to Wayback Machine Save Page Now (SPN2) and wait for result.

    If the URL already has a fresh snapshot, returns it without submitting.
    Otherwise submits and polls until success or timeout.
    """
    # Check first — no need to re-save a fresh snapshot
    existing = await wayback_check(url)
    if existing.status == "found":
        log.debug("wayback: already have fresh snapshot for %s", url)
        return existing

    log.info("wayback: submitting %s to SPN2 …", url)
    try:
        r = requests.post(
            _SAVE_URL,
            data={"url": url, "capture_outlinks": 0, "capture_screenshot": 0},
            timeout=_HTTP_TIMEOUT,
            headers={
                "User-Agent": "BeaconDirectoryBot/1.0",
                "Accept": "application/json",
            },
        )
        # SPN2 returns 200 with JSON or a redirect; handle both
        if r.status_code not in (200, 302):
            # Some errors return non-JSON — capture text
            return WaybackResult(url=url, snapshot_url=None, timestamp=None,
                                 status="error",
                                 error=f"HTTP {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except Exception:
            # Unauthenticated SPN sometimes returns HTML; treat as pending
            data = {}
    except Exception as exc:
        log.warning("wayback_save submit failed for %s: %s", url, exc)
        return WaybackResult(url=url, snapshot_url=None, timestamp=None,
                             status="error", error=str(exc))

    job_id = data.get("job_id")
    if not job_id:
        # Older SPN1 response — extract snapshot from headers or URL
        snap = _extract_snap_from_response(r, url)
        if snap:
            return WaybackResult(url=url, snapshot_url=snap, timestamp=None, status="saved")
        return WaybackResult(url=url, snapshot_url=None, timestamp=None,
                             status="pending", error="no job_id in SPN2 response")

    # Poll for completion
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            status_r = requests.get(
                _STATUS_URL.format(job_id=job_id),
                timeout=_HTTP_TIMEOUT,
                headers={"User-Agent": "BeaconDirectoryBot/1.0",
                         "Accept": "application/json"},
            )
            sd = status_r.json()
        except Exception as exc:
            log.debug("wayback poll error: %s", exc)
            continue

        st = sd.get("status", "")
        if st == "success":
            ts = sd.get("timestamp", "")
            orig = sd.get("original_url", url)
            snap = f"https://web.archive.org/web/{ts}/{orig}" if ts else None
            log.info("wayback: saved %s → %s", url, snap)
            return WaybackResult(url=url, snapshot_url=snap, timestamp=ts, status="saved")
        if st == "error":
            log.warning("wayback SPN2 error for %s: %s", url, sd.get("exception", ""))
            return WaybackResult(url=url, snapshot_url=None, timestamp=None,
                                 status="error", error=sd.get("exception", "SPN2 error"))
        # status == "pending" — keep polling

    log.warning("wayback: timed out waiting for SPN2 job %s (%s)", job_id, url)
    return WaybackResult(url=url, snapshot_url=None, timestamp=None, status="pending")


def content_hash(text: str) -> str:
    """SHA-256 of page text content — use for evidence retrieval_integrity."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_snap_from_response(r: requests.Response, url: str) -> Optional[str]:
    """Try to find a snapshot URL in the SPN1-style response."""
    # Location header on redirect
    loc = r.headers.get("Location", "")
    if "web.archive.org/web/" in loc:
        return loc
    # Content-Location
    cl = r.headers.get("Content-Location", "")
    if "web.archive.org/web/" in cl:
        return "https://web.archive.org" + cl if cl.startswith("/") else cl
    return None


# ---------------------------------------------------------------------------
# Tool schemas for agent use
# ---------------------------------------------------------------------------

WAYBACK_CHECK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wayback_check",
        "description": (
            "Check if a URL already has a recent Wayback Machine snapshot (within 30 days). "
            "Use before wayback_save to avoid re-submitting pages that are already archived."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to check"},
            },
            "required": ["url"],
        },
    },
}

WAYBACK_SAVE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wayback_save",
        "description": (
            "Archive a URL with the Wayback Machine Save Page Now (SPN2). "
            "Returns the snapshot_url to use as evidence archived_snapshot. "
            "Use after navigating to and extracting facts from a page — "
            "the snapshot proves the page content at the time of investigation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to archive"},
            },
            "required": ["url"],
        },
    },
}


async def handle_wayback_check(args: dict) -> str:
    import json
    result = await wayback_check(args["url"])
    return json.dumps(result.as_dict())


async def handle_wayback_save(args: dict) -> str:
    import json
    result = await wayback_save(args["url"])
    return json.dumps(result.as_dict())
