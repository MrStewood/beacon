# Beacon Source Policy

## Canonical Sources

The only hand-edited source files are:

```
source/approved/**/*.yaml     # Approved canonical records
source/overrides/**/*.yaml    # Manual corrections (take precedence)
source/candidates/**/*.yaml   # Unpublished candidates under research/verification (schema/candidate.schema.json)
```

Candidates are never canonical. A candidate only becomes `source/approved/`
content by passing every gate in TRUST_SCORING.md and having its `decision`
block recomputed and matched by `scripts/validate_candidate.py` in CI.

## Source Hierarchy

1. `source/overrides/` — Manual corrections (highest priority)
2. `source/approved/` — Canonical records

## What is Generated (Do Not Edit)

The following are generated from canonical sources:
- `data/` — All JSON and CSV files
- `pages/` — All HTML pages
- `print/` — All print pages
- `sitemap.xml`

## Evidence Standards

Full claim-level scoring, source tiers (A-F), caps, and formulas: see
[TRUST_SCORING.md](TRUST_SCORING.md). Summary:

- Sources are classified by tier (A=authoritative primary … F=discovery-only)
  **per claim type**, not once for the whole record.
- Two sources that copied the same upstream feed share one `chain_id` and
  count as **one** evidence chain for corroboration/independence, not two.
- Not acceptable as evidence for any claim: search engine snippets,
  AI-generated content, map listings alone, social media posts, unattributed
  third-party mentions. These may only be used to locate a better source.

## Migration

The legacy CSV was archived outside the repository during the clean resource reset.
All new records must use the YAML format in `source/approved/`.
