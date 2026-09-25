#!/usr/bin/env python3
"""
Beacon lead generation pre-search.

Runs all category searches for a given ZIP code via SearXNG, filters out
already-evaluated URLs, and writes a one-shot extraction prompt for the model.

Usage:
    python3 leads/presearch.py <zip> [--out /tmp/presearch_<zip>.json]
    python3 leads/presearch.py <zip> --prompt   # also build the prompt file

Outputs:
    /tmp/beacon_presearch_<zip>.json   raw search results (filtered)
    /tmp/beacon_prompt_<zip>.md        one-shot model prompt (with --prompt)
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ZIPS_PATH = REPO_ROOT / "data" / "census" / "us-zips.json"
SEEN_REGISTRY = Path(__file__).parent / "seen_urls.json"
SEARXNG = "http://searxng:8080"
MAX_RESULTS_PER_QUERY = 15
TOP_N_FOR_PROMPT = 5  # per category in the prompt


# 2 queries per category — SearXNG fans out to all enabled engines per query,
# so 2 well-chosen queries + 11 engines gives broad coverage without hammering.
CATEGORY_QUERIES = {
    "food":              ["{county} County {state_name} food bank food pantry",
                          "{city} {state} soup kitchen meal program SNAP WIC"],
    "shelter":           ["{county} County {state_name} homeless shelter emergency shelter",
                          "{city} {state} warming center overnight shelter"],
    "housing":           ["{county} County {state_name} transitional housing rent assistance",
                          "{city} {state} housing authority Section 8 affordable housing"],
    "health":            ["{county} County {state_name} community health center free clinic",
                          "{city} {state} health department Medicaid dental"],
    "mental-health":     ["{county} County {state_name} mental health counseling center",
                          "{city} {state} behavioral health psychiatric services"],
    "addiction":         ["{county} County {state_name} addiction treatment detox rehab",
                          "{city} {state} MAT program substance abuse recovery"],
    "crisis":            ["{county} County {state_name} crisis hotline domestic violence shelter",
                          "{city} {state} crisis center emergency services rape crisis"],
    "family":            ["{county} County {state_name} childcare assistance youth services",
                          "{city} {state} family services foster care parenting"],
    "legal":             ["{county} County {state_name} legal aid free attorney",
                          "{city} {state} victim advocacy court help expungement"],
    "documents":         ["{county} County {state_name} ID assistance Social Security office",
                          "{city} {state} birth certificate document help"],
    "education":         ["{county} County {state_name} GED adult education literacy",
                          "{city} {state} trade school workforce training"],
    "jobs":              ["{county} County {state_name} job training employment services",
                          "{city} {state} workforce development career center"],
    "transportation":    ["{county} County {state_name} transportation assistance NEMT",
                          "{city} {state} bus ride program medical transport"],
    "utility-assistance":["{county} County {state_name} utility bill help LIHEAP",
                          "{city} {state} electric water assistance shutoff prevention"],
    "clothing":          ["{county} County {state_name} clothing bank free clothes hygiene",
                          "{city} {state} thrift donation supplies blankets"],
    "community":         ["{county} County {state_name} community support church outreach",
                          "{city} {state} peer support faith ministry mentoring"],
    "veterans":          ["{county} County {state_name} veteran services VSO",
                          "{city} {state} VA office veteran housing employment"],
}

UMBRELLA_QUERIES = [
    "{county} County {state_name} community resources social services directory",
    "211 help {county} County {state} United Way community action agency",
]


def lookup_zip(zip_code: str) -> dict:
    data = json.load(open(ZIPS_PATH))
    if zip_code not in data:
        print(f"ERROR: ZIP {zip_code} not found in us-zips.json", file=sys.stderr)
        sys.exit(1)
    info = data[zip_code]
    info["zip"] = zip_code
    return info


def load_seen() -> set:
    if SEEN_REGISTRY.exists():
        reg = json.load(open(SEEN_REGISTRY))
        print(f"Loaded {len(reg)} already-evaluated URLs to skip", file=sys.stderr)
        return set(reg.keys())
    return set()


def search(query: str, max_results: int = MAX_RESULTS_PER_QUERY) -> list:
    q = urllib.parse.quote(query)
    cmd = f'curl -s --max-time 10 "{SEARXNG}/search?q={q}&format=json"'
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        data = json.loads(out)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:300],
            }
            for r in data.get("results", [])[:max_results]
        ]
    except Exception as e:
        return []


def run_presearch(zip_info: dict, seen_urls: set) -> dict:
    z = zip_info
    fmt = dict(
        zip=z["zip"],
        city=z["city"],
        county=z["county"],
        state=z["state"],
        state_name=z["state_name"],
    )

    all_results = {}
    session_seen = set()

    def run_category(cat: str, queries: list[str]) -> list:
        results = []
        for tmpl in queries:
            q = tmpl.format(**fmt)
            print(f"  [{cat}] {q}", file=sys.stderr)
            for r in search(q):
                url = r.get("url", "")
                if url and url not in session_seen and url not in seen_urls:
                    session_seen.add(url)
                    r["category_hint"] = cat
                    r["query"] = q
                    results.append(r)
            time.sleep(1.5)  # avoid hammering any single engine
        return results

    # Umbrella first
    umbrella_q = [t.format(**fmt) for t in UMBRELLA_QUERIES]
    all_results["umbrella"] = run_category("umbrella", umbrella_q)

    for cat, templates in CATEGORY_QUERIES.items():
        all_results[cat] = run_category(cat, templates)

    return {
        "zip": z["zip"],
        "city": z["city"],
        "county": z["county"],
        "state": z["state"],
        "state_name": z["state_name"],
        "searched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_unique_urls": len(session_seen),
        "skipped_seen_urls": len(seen_urls),
        "results_by_category": all_results,
    }


def build_prompt(presearch: dict, known_names: list[str] = None) -> str:
    z = presearch
    area = f"{z['city']}, {z['county']} County, {z['state_name']} (ZIP {z['zip']})"
    cats = [c for c in presearch["results_by_category"] if c != "umbrella"]
    cat_list = "|".join(cats)

    lines = [
        f"You are a community resource researcher for Beacon, a directory for people in need in {area}.",
        "",
        "ALL search results are pre-gathered below. Do NOT call any tools. Do NOT search. Use ONLY this data.",
        "Produce ONE JSON object and stop. No preamble, no explanation — only the JSON.",
        "",
    ]

    if known_names:
        lines.append(f"Skip these already-known resources: {'; '.join(known_names[:30])}")
        lines.append("")

    lines.append(
        f'Return exactly: {{"zip":"{z["zip"]}","county":"{z["county"]}","state":"{z["state"]}",'
        f'"resources_found":[{{'
        f'"name":"...","category":"{cat_list}",'
        f'"description":"1-2 sentences","phones":[],"address":null,"url":null,'
        f'"hours":null,"eligibility":null,"source_urls":[],'
        f'"county":"{z["county"]}","state":"{z["state"]}","zip":"{z["zip"]}",'
        f'"verification_status":"unverified","confidence":"high|medium|low"'
        f'}}],"categories_searched":[...],"notes":"..."}}'
    )
    lines += [
        "",
        "=" * 60,
        f"PRE-GATHERED SEARCH RESULTS FOR {area}",
        "=" * 60,
    ]

    for cat, results in presearch["results_by_category"].items():
        if not results:
            continue
        lines.append(f"\n## {cat.upper()} ({len(results)} results)")
        for r in results[:TOP_N_FOR_PROMPT]:
            lines.append(f"- {r['title']} | {r['url']}")
            if r.get("snippet"):
                lines.append(f"  {r['snippet'][:200]}")

    return "\n".join(lines)


def load_known_names(zip_code: str) -> list[str]:
    """Load names already in dedup to pass as exclusions."""
    dedup_path = SEEN_REGISTRY.parent / "dedup.json"
    if not dedup_path.exists():
        return []
    try:
        d = json.load(open(dedup_path))
        return [v.get("name", "") for v in d.values() if v.get("name")]
    except Exception:
        return []


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    zip_code = sys.argv[1]
    build_prompt_flag = "--prompt" in sys.argv

    zip_info = lookup_zip(zip_code)
    print(
        f"Searching {zip_info['city']}, {zip_info['county']} County, {zip_info['state_name']} ({zip_code})",
        file=sys.stderr,
    )

    seen = load_seen()
    results = run_presearch(zip_info, seen)

    out_file = f"/tmp/beacon_presearch_{zip_code}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print(
        f"Done. {results['total_unique_urls']} new URLs "
        f"({results['skipped_seen_urls']} skipped). Saved to {out_file}",
        file=sys.stderr,
    )

    if build_prompt_flag:
        known = load_known_names(zip_code)
        prompt = build_prompt(results, known)
        prompt_file = f"/tmp/beacon_prompt_{zip_code}.md"
        with open(prompt_file, "w") as f:
            f.write(prompt)
        chars = len(prompt)
        print(
            f"Prompt: {chars:,} chars (~{chars//4:,} tokens). Saved to {prompt_file}",
            file=sys.stderr,
        )
        print(prompt_file)
    else:
        print(out_file)
