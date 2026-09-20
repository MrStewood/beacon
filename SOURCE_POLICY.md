# Beacon Source Policy

## Canonical Sources

The only hand-edited source files are:

```
source/approved/**/*.yaml     # Approved canonical records
source/overrides/**/*.yaml    # Manual corrections (take precedence)
```

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

### Acceptable Sources
- Official provider website
- Government directory
- Direct phone confirmation
- 211 directory
- Licensed provider directory

### Not Acceptable as Evidence
- Search engine snippets
- AI-generated content
- Map listings alone
- Social media posts
- Third-party mentions without verification

## Migration

The legacy `source/raw/kentucky.csv` may remain as historical reference.
All new records must use the YAML format in `source/approved/`.
