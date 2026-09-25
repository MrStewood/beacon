#!/usr/bin/env python3
"""
Persistent URL registry for Beacon lead generation.

Tracks every URL the model has evaluated, keyed by URL, with outcome and run
metadata, so repeat runs can skip work that is already done.

Usage:
  python3 leads/seen_urls.py show                 # print stats (default)
  python3 leads/seen_urls.py rebuild              # rebuild from all processed runs
  python3 leads/seen_urls.py update <processed>   # add URLs from one processed run
"""

import json
import glob
import sys
import os

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "seen_urls.json")
RUNS_GLOB = os.path.join(os.path.dirname(__file__), "runs", "**", "*-processed.json")

OUTCOME_FIELDS = [
    "new_leads",
    "duplicates",
    "near_duplicates",
    "rejected",
    "out_of_area",
    "insufficient_info",
    "reconsider_rejected",
    "possible_related_programs",
]


def load() -> dict:
    if os.path.exists(REGISTRY_PATH):
        return json.load(open(REGISTRY_PATH))
    return {}


def save(registry: dict) -> None:
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=True)


def rebuild() -> dict:
    """Rebuild registry from scratch by scanning all processed run files."""
    registry = {}
    for path in sorted(glob.glob(RUNS_GLOB, recursive=True)):
        d = json.load(open(path))
        run_id = d.get("run_id", "?")
        zip_code = d.get("zip", "?")
        for outcome in OUTCOME_FIELDS:
            for item in d.get(outcome, []):
                name = item.get("name", "?")
                all_urls = list(item.get("source_urls") or [])
                if item.get("url"):
                    all_urls.append(item["url"])
                for url in all_urls:
                    if url and url not in registry:
                        registry[url] = {
                            "outcome": outcome,
                            "name": name,
                            "run_id": run_id,
                            "zip": zip_code,
                        }
    return registry


def update_from_processed(processed_path: str) -> dict:
    """Add URLs from a single processed file into the existing registry."""
    registry = load()
    d = json.load(open(processed_path))
    run_id = d.get("run_id", "?")
    zip_code = d.get("zip", "?")
    added = 0
    for outcome in OUTCOME_FIELDS:
        for item in d.get(outcome, []):
            name = item.get("name", "?")
            all_urls = list(item.get("source_urls") or [])
            if item.get("url"):
                all_urls.append(item["url"])
            for url in all_urls:
                if url and url not in registry:
                    registry[url] = {
                        "outcome": outcome,
                        "name": name,
                        "run_id": run_id,
                        "zip": zip_code,
                    }
                    added += 1
    return registry, added


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"

    if cmd == "rebuild":
        registry = rebuild()
        save(registry)
        by_outcome = {}
        for info in registry.values():
            by_outcome.setdefault(info["outcome"], 0)
            by_outcome[info["outcome"]] += 1
        print(f"Rebuilt registry: {len(registry)} URLs")
        for k, v in sorted(by_outcome.items()):
            print(f"  {k}: {v}")
        print(f"Saved to {REGISTRY_PATH}")

    elif cmd == "show":
        registry = load()
        by_outcome = {}
        for info in registry.values():
            by_outcome.setdefault(info["outcome"], 0)
            by_outcome[info["outcome"]] += 1
        print(f"Registry: {len(registry)} URLs")
        for k, v in sorted(by_outcome.items()):
            print(f"  {k}: {v}")

    elif cmd == "update" and len(sys.argv) > 2:
        registry, added = update_from_processed(sys.argv[2])
        save(registry)
        print(f"Updated registry: +{added} URLs, total {len(registry)}")

    else:
        print(__doc__)
        sys.exit(1)
