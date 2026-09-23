# Beacon Lead Discovery — How to Use

## End-to-End Workflow

### 1. Generate a research prompt for a ZIP code

```bash
python3 leads/research.py prompt 41640
```

Output: JSON with `prompt` field containing the full search instructions, plus metadata (county, state, categories, existing resources to exclude).

### 2. Feed the prompt to a research agent

The agent uses **Playwright MCP browser tools** to search the web:

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Go to Google, visit directories |
| `browser_type` | Enter search queries |
| `browser_click` | Follow links, click results |
| `browser_snapshot` | Read page content (accessibility tree) |
| `browser_back` | Return to results |

**Search depth:** Page 1 always, page 2 if thin, page 3+ for zeros.
**Directory extraction:** Mandatory — extract every resource from directory pages.
**Counting:** Only count new + unique + verified resources.

### 3. Save agent results, process, and commit

```bash
# Save results
cat > leads/results_41640.json << 'ENDJSON'
{ ... agent JSON ... }
ENDJSON

# Process (dedup + save)
python3 leads/research.py process 41640 leads/results_41640.json

# Commit to GitHub
git add leads/leads_41640_*.json leads/dedup.json
git commit -m "leads: 41640 (Clay, KY) — 12 new, 3 duplicates"
git push origin main

# Clean up raw results
rm leads/results_41640.json
```

This will:
- Deduplicate against existing Beacon data
- Deduplicate against previously discovered leads
- Separate new leads from duplicates
- Flag out-of-area resources for future expansion
- Save leads to `leads/leads_41640_YYYY-MM-DD.json`
- Update `leads/dedup.json`

### 4. Review results

```bash
# See what's been processed so far
python3 leads/research.py status

# List all discovered leads
python3 leads/research.py leads

# See resources found outside the target ZIP
python3 leads/research.py out-of-area
```

## Deduplication

Three levels of dedup:
1. **Exact match**: Same normalized name + same phone digits → already in Beacon
2. **Lead match**: Same key in `dedup.json` → already discovered
3. **Near-duplicate**: Same normalized name but different phone → flagged for review

## Out-of-Area Tracking

If a resource is found that serves the target county but is physically located in a different ZIP, it's flagged in `out_of_area`. These are leads for future ZIP expansion — when you research that ZIP, the resource will already be known.

## Census Data & Needs Assessment

The lead system uses US Census Bureau data for nationwide ZIP coverage:

### ZIP Lookup (33,048 ZIP codes)

All US ZIP codes are mapped to county/city/state via `data/census/us-zips.json`.
Source: Census Bureau via [scpike/us-state-county-zip](https://github.com/scpike/us-state-county-zip).

```bash
# Rebuild from source CSV
python3 data/census/build_us_zips.py
```

### Census Socioeconomic Indicators

ACS 5-Year data for poverty, unemployment, SNAP, disability, income, and more.

```bash
# Requires free Census API key: https://api.census.gov/data/key_signup.html
CENSUS_API_KEY=KEY python3 data/census/census_indicators.py
```

### Needs Analysis

Composite need scoring (0-100) per ZIP based on poverty, SNAP, unemployment, disability, income, and renter rates. Cross-references against existing Beacon resource coverage.

```bash
# Generate needs analysis (requires us-zips-census.json first)
python3 data/census/needs_score.py
```

### Querying Needs Data

```bash
# Show Census needs indicators for a ZIP
python3 leads/research.py needs 40701

# Show state-level summary
python3 leads/research.py needs KY
```

PO Box-only ZIPs (no physical area) resolve to "Unknown" — this is expected.

## Categories

All 17 Beacon categories are searched:

| Category | What to look for |
|----------|-----------------|
| food | Food banks, pantries, SNAP, WIC, soup kitchens |
| shelter | Emergency shelters, warming centers |
| housing | Transitional housing, Section 8, rent assistance |
| health | Community health centers, free clinics, Medicaid |
| mental-health | Counseling, therapy, crisis counseling |
| addiction | Treatment centers, detox, MAT, recovery |
| crisis | Hotlines, DV shelters, suicide prevention |
| family | Childcare, foster care, youth services |
| legal | Legal aid, expungement, court help |
| documents | ID assistance, birth certificates, SSA |
| education | GED, adult education, literacy |
| jobs | Job training, workforce development |
| transportation | Bus passes, ride programs, NEMT |
| utility-assistance | LIHEAP, bill help, shutoff prevention |
| clothing | Clothing banks, hygiene kits |
| community | Peer support, mentoring, faith outreach |
| veteran | VSO, VA, veteran-specific services |
