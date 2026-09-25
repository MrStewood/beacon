# Beacon Lead Discovery — How to Use

## Goal

For a target ZIP code, discover community resources across all 17 Beacon
categories, save them as a results file, run them through the dedup pipeline,
post one summary comment on the task, and set the task to done.

There is no fixed step sequence. The sections below are the tools you have and
the rules that bound the work — you decide what to run and in what order.

## Tools

### Search: SearXNG through `curl`

Discovery is `curl`, never a browser: search engines block headless browsers.

```bash
Q=$(python3 -c "import urllib.parse;print(urllib.parse.quote('Laurel County Kentucky food bank food pantry'))")
curl -s "http://searxng:8080/search?q=$Q&format=json"
```

Response shape: `{"results": [{"title": "...", "url": "...", "content": "..."}, ...]}`.

Query shapes that work: `<county> County <state> <service>`, `<city> <state> <service>`,
`<org name> <city> <state> phone`.

### Read a source page: browser tools

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Visit a resource site or directory listing |
| `browser_snapshot` | Read page content as an accessibility tree |
| `browser_evaluate` | Extract structured data with JavaScript |
| `browser_back` | Return to a directory after visiting a resource |

Use these to confirm details on the organization's own site. A search snippet is
not evidence and a directory listing is not provider confirmation.

### See what is already known

```bash
# Target ZIP, categories, exclusion list, known-lead counts — writes the run
# manifest and prompt payload under leads/runs/<zip>/
python3 leads/research.py plan 40744

# Same payload printed to stdout without writing a run
python3 leads/research.py prompt 40744

python3 leads/research.py status        # what has been processed
python3 leads/research.py leads         # every lead already in the queue
python3 leads/research.py out-of-area   # county-serving leads found in other ZIPs
python3 leads/seen_urls.py show         # URLs already evaluated — skip them
```

`plan`/`prompt` include the names and URLs you must not rediscover. Checking
these first is the cheapest way to avoid redoing known work.

### Write results

One file per run: `leads/results_<zip>.json`

```json
{
  "zip": "40744",
  "county": "...",
  "state": "...",
  "resources_found": [
    {
      "name": "...",
      "category": "food|shelter|housing|health|mental-health|addiction|crisis|family|legal|documents|education|jobs|transportation|utility-assistance|clothing|community|veteran",
      "description": "1-2 sentences",
      "phones": [],
      "address": null,
      "url": null,
      "hours": null,
      "eligibility": null,
      "source_urls": [],
      "county": "...",
      "state": "...",
      "zip": "...",
      "verification_status": "unverified",
      "confidence": "high|medium|low"
    }
  ]
}
```

A resource needs a name plus at least one of phone, address, or url. Never
invent contact details.

### Process: dedup and save

```bash
python3 pilot/routines.py lead-generation 40744 leads/results_40744.json
```

Runs the safety gate, then `leads/research.py process`, then refreshes the
seen-URL registry. Prints a `{"ok": true, ...}` summary containing
`processed_file`. What it does for you:

- Deduplicate against published Beacon records, current pilot cases, previously
  discovered leads, prior run artifacts, and rejected leads
- Classify every record: `new`, `duplicate_*`, `near_duplicate_review`,
  `possible_related_program`, `out_of_area_new`, `insufficient_info`, or `policy_rejected`
- Save unique run artifacts to `leads/runs/<zip>/leadgen-<zip>-<timestamp>-*.json`
- Update `leads/dedup.json`

### Finish

Post ONE task comment containing that summary JSON and the `processed_file`
path, then set the task status to done.

## Working efficiently

- Look before you search: `plan` plus `seen_urls.py show` costs two calls and
  stops you rediscovering known leads and URLs.
- Batch searches — several `curl` calls in a single bash invocation is one tool
  round trip instead of five.
- Read a page once. Take what you need, move on, do not re-read files you just wrote.
- Write the results file as soon as coverage is good enough and process it
  immediately, so a later failure cannot lose the run.
- Stop when all 17 categories are covered or ruled out, not when you run out of ideas.

## Hard limits

Discovery only. These are not negotiable:

- Never invent a phone number, address, hours, eligibility rule, or service
  area. Use `null` when it cannot be established.
- Minimum lead: `name` plus `url` or `source_urls`.
- Do not create pilot cases. Do not edit `source/`, or any generated file
  under `data/`, `pages/`, `print/`.
- Do not commit, push, or open pull requests from this task — artifacts are
  committed separately.
- Never record a confidential shelter location or anything about an individual
  client or help seeker.
- Stop and mark the task blocked if the tools you need are unavailable.

## Deduplication

Lead generation checks every durable place a resource can already exist:
1. **Published records**: `source/approved/**/*.yaml` and generated resource JSON.
2. **Pilot cases**: every `pilot/cases/*.json` state, including `received` and active work.
3. **Lead queue**: `leads/dedup.json`.
4. **Prior run artifacts**: `leads/runs/<zip>/*-processed.json` and legacy `leads/leads_*.json`.
5. **Rejected leads**: `pilot/rejected/*.json` and rejected dedup statuses.

Classifications are explicit: `new`, `duplicate_existing_resource`, `duplicate_existing_case`, `duplicate_existing_lead`, `duplicate_prior_run`, `previously_rejected`, `reconsider_rejected`, `near_duplicate_review`, `possible_related_program`, `out_of_area_new`, `insufficient_info`, or `policy_rejected`.

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
