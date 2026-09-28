# Beacon — AI Onboarding

**What**: Community resource directory (food, shelter, health, crisis, etc.) for people in need.  
**Goal**: AI-managed pipeline that discovers, verifies, and publishes resource records with human oversight.  
**State**: Pre-release. No records published yet. Infrastructure ready. Awaiting first approved resources.  
**Repo**: `github.com/MrStewood/beacon` · GitHub Pages: `mrstewood.github.io/beacon/`

---

## Repository Map

```
beacon/
├── source/
│   ├── approved/          ← CANONICAL. Only records here appear on the public site.
│   └── candidates/        ← In-progress. CI validates; human approves PR to promote.
│
├── leads/
│   ├── research.py        ← CLI: plan/prompt/process/status/leads/needs subcommands
│   ├── seen_urls.py       ← URL dedup registry (prevents re-evaluating known URLs)
│   ├── dedup.json         ← Lead dedup state (v2 format)
│   ├── runs/<zip>/        ← GITIGNORED runtime artifacts per ZIP run
│   ├── investigations/    ← GITIGNORED investigation outputs
│   ├── WORKFLOW.md        ← Lead generation operating guide (read before researching)
│   ├── INVESTIGATION.md   ← Deep-research operating guide
│   └── EXPANSION.md       ← Geographic priority plan (Wave 0→7)
│
├── pilot/
│   ├── stage_controller.py ← Manual advance/status/reset of pipeline cases
│   ├── routines.py         ← Safety gate + lead-generation routine
│   ├── manual_pilot.json   ← Pilot config (switches, limits, execution level)
│   ├── cases/              ← GITIGNORED per-case JSON state files
│   └── audit/              ← GITIGNORED audit trail NDJSON
│
├── scripts/
│   ├── build.py            ← Entry point: runs all steps → assembles _site/
│   ├── build_from_yaml.py  ← Reads source/approved/**/*.yaml → data/
│   ├── build_pages.py      ← Generates pages/ (resource/county/need HTML)
│   ├── build_print.py      ← Generates print/
│   ├── validate.py         ← Schema + business rules on data/resources.json
│   ├── validate_candidate.py ← CI gate: recomputes trust score from raw evidence
│   ├── validate_sources.py ← Separation-of-duties check on approved resources
│   ├── trust_scoring.py    ← Deterministic claim/record scoring (see §Trust)
│   ├── workflow_state.py   ← Enforced state machine (raises IllegalTransition)
│   ├── sign_candidate.py   ← Director signs the publication decision
│   ├── geocode.py          ← Address → lat/lon
│   └── config.py           ← Shared path constants (REPO_ROOT, DATA_DIR, etc.)
│
├── schema/
│   ├── resource.schema.json     ← Published record schema
│   ├── resource.schema.v3.json  ← v3 (current); validation uses this
│   └── candidate.schema.json    ← Candidate record schema
│
├── data/
│   ├── census/            ← Reference data (NOT in _site/). Contains:
│   │   ├── us-zips.json          33K ZIP→county/city/state mappings
│   │   ├── us-zips-census.json   ACS socioeconomic data per ZIP (19 MB)
│   │   └── needs-analysis.json   Composite need score 0-100 per ZIP (14 MB)
│   └── [resources.json etc.]  ← GITIGNORED generated outputs
│
├── tests/                 ← pytest suite (86 pass, 57 skip on empty dataset)
├── assets/, embed/        ← Static web assets
├── index.html             ← Public search UI
├── _site/                 ← GITIGNORED built site (deployed to GitHub Pages)
└── .env                   ← NEVER COMMIT. Services config (see §Services).
```

**Gitignored** (never commit): `_site/`, `data/resources*`, `data/index*`, `data/catalog*`,
`data/v3/`, `data/change-report*`, `pages/`, `print/`, `leads/runs/`, `leads/investigations/`,
`pilot/cases/`, `pilot/audit/`, `pilot/rejected/`.

---

## Pipeline — End to End

```
RESEARCH                    PIPELINE                        PUBLISH
────────────────────────    ────────────────────────────    ──────────────────────
1. leads/WORKFLOW.md        3. source/candidates/<id>.yaml  7. source/approved/<id>.yaml
   (read before starting)      (AI writes; opens PR)           (PR merged by human)
                                     ↓                               ↓
2. leads/research.py        4. CI: validate + recompute     8. CI build on main push
   plan <zip>                  trust score from evidence        → _site/ → GitHub Pages
   → leads/runs/<zip>/      5. Human reviews PR
     leadgen-*.json         6. Human approves + merges
```

### Workflow States (enforced by `scripts/workflow_state.py`)

Happy path (linear):
```
lead-received → intake-classified → duplicate-checked
  → research-a-locked → research-b-locked → evidence-compared
  → verified → risk-verification-complete → policy-checked
  → trust-scored → decision-signed → yaml-created
  → pr-opened → ci-passed → merged → deployed
  → production-verified → monitoring → reverification-due
  → (loops back to duplicate-checked)
```

Exception exits (from any working state): `quarantined` | `temporarily-suppressed` | `rejected` | `system-paused`

### Role → Transition Map

| Role | Transition(s) |
|------|--------------|
| `intake` | lead-received → intake-classified → duplicate-checked |
| `research-a` | duplicate-checked → research-a-locked |
| `research-b` | research-a-locked → research-b-locked |
| `evidence-comparator` | research-b-locked → evidence-compared |
| `verifier` | evidence-compared → verified → risk-verification-complete |
| `second-verifier` | verified → risk-verification-complete |
| `policy-engine` | risk-verification-complete → policy-checked |
| `scoring-engine` | policy-checked → trust-scored |
| `director` | trust-scored → decision-signed |
| `publisher` | decision-signed → yaml-created → pr-opened |
| `ci` | pr-opened → ci-passed → merged → deployed |
| `deployment-monitor` | deployed → production-verified → monitoring |
| `scheduler` | monitoring → reverification-due |

### Role Separation (code-enforced — cannot be bypassed)

`workflow_state.py` raises `IllegalTransition` on violation. Not advisory.

| Role | Must differ from |
|------|-----------------|
| `research-b` | `research-a` |
| `verifier` | `research-a`, `research-b` |
| `second-verifier` | `research-a`, `research-b`, `verifier` |
| `director` | `research-a`, `research-b`, `verifier`, `second-verifier` |
| `publisher` | all of the above + `director` |

---

## Trust Scoring

Source: `scripts/trust_scoring.py` · Policy version: `1.0.0`

### Source Authority Tiers (A=best)

| Tier | Authority | Examples |
|------|-----------|---------|
| A | 35 | Official provider website, government database |
| B | 30 | Government agency listing |
| C | 24 | 211 directory, licensing body |
| D | 17 | Nonprofit aggregator, map listing |
| E | 8 | News article |
| F | 2 | Search snippet (CANNOT verify a claim alone) |

### Claim Score Components (0–100)
Source authority (0–35) + directness (0–20) + freshness (0–15) + corroboration (0–15) + chain independence (0–10) + retrieval integrity (0–5)

### Freshness Windows (acceptable, stale in days)

| Class | Acceptable | Stale |
|-------|-----------|-------|
| `crisis` | 30 | 60 |
| `operating_status` | 90 | 180 |
| `hours_phone` | 90 | 180 |
| `eligibility` | 180 | 365 |
| `address` | 180 | 365 |
| `service_description` | 365 | 730 |
| `stable_program_identity` | 365 | 730 |

### Publication Thresholds (record_min / essential_claim_min)

| Risk tier | Record | Essential claim |
|-----------|--------|----------------|
| `low` | 80 | 75 |
| `elevated` | 90 | 85 |
| `critical` | 95 | 90 |

### Conflict Penalties (subtracted from record score)

| Type | Penalty |
|------|---------|
| `wording` | 0–5 |
| `nonessential-detail` | 5–10 |
| `hours-eligibility-coverage` | 20 |
| `phone-address-status` | 30 |
| `closure-evidence` | 40 |
| `privacy-safety` | blocks publication entirely |

Record score = 70% essential claims + 30% material claims. CI **recomputes** this from raw evidence; the agent's stated decision is never trusted.

---

## Resource Schema

**Required**: `id`, `name`, `county`, `status`

Key field enums:

| Field | Values |
|-------|--------|
| `needs` | addiction, clothing, community, crisis, documents, education, family, food, health, housing, jobs, legal, mental-health, shelter, transportation, utility-assistance, veterans |
| `service_types` | hotline, walk-in, appointment, residential, outpatient, mobile, online, peer-led, faith-based, government |
| `populations` | anyone, families, women, men, youth, seniors, veterans, lgbtq+, disability, re-entry, pregnant, substance-use, recovery |
| `status` | active, needs-verification, closed |
| `verification_status` | unverified, auto-inferred, website-checked, phone-confirmed, in-person-verified |
| `confidence` | high, medium, low |

Full schema: `schema/resource.schema.v3.json` · Candidate schema: `schema/candidate.schema.json`  
Candidate required fields: `candidate_id`, `workflow_state`, `risk_tier`, `resource`, `claims`, `research_packages`, `policy_version`

---

## Hard Rules

These are inviolable. Stop and flag if any would be violated.

1. **Never invent** a phone number, address, hours, eligibility rule, or service area. Use `null`.
2. **Minimum viable lead**: `name` + at least one of (`phone`, `address`, `url`).
3. **Never publish a confidential location** (DV shelters, crisis safe houses).
4. **Never record info about individual clients** or help seekers.
5. **Never write directly to `source/approved/`**. Only a human-approved PR can promote a candidate.
6. **Never commit to `main` directly**. All changes via feature branch → PR.
7. **Never self-merge**. A distinct human (or Quality Agent) must approve every PR.
8. **Never close a resource on one broken website or unanswered call**. Requires corroboration.
9. **Sensitive resources require explicit human approval**: 911/988/211, crisis hotlines, DV services, children's services, medical intake, confidential shelters, closures.
10. **Search snippets (Tier F) cannot verify a claim alone** — they raise a lead, not evidence.
11. **Never re-commit generated files** (`data/resources.json`, `pages/`, `print/`, `_site/`). They are gitignored.

---

## Common Operations

### Research a ZIP code

```bash
# See what's known, get prompt payload, check seen URLs
python3 leads/research.py plan 40744
python3 leads/seen_urls.py show

# Search (SearXNG — curl only, not browser; engines block headless)
Q=$(python3 -c "import urllib.parse;print(urllib.parse.quote('Laurel County Kentucky food bank'))")
curl -s "http://localhost:8888/search?q=$Q&format=json"

# Write results file
# leads/results_<zip>.json (format: see leads/WORKFLOW.md)

# Process (dedup, classify, save artifacts)
python3 pilot/routines.py lead-generation 40744 leads/results_40744.json
```

### Check pilot safety gate

```bash
python3 pilot/routines.py safety
```

### Build and validate locally

```bash
python3 scripts/build.py          # full build → _site/
python3 scripts/build.py --test   # + pytest
python3 scripts/validate.py       # validate data/ only
python3 scripts/validate_candidate.py --all   # validate all candidates
pytest tests/ -v
```

### Validate a candidate file

```bash
python3 scripts/validate_candidate.py source/candidates/<county>/<id>.yaml
```

### Serve site locally

```bash
python3 -m http.server 8000 --directory _site
# http://localhost:8000
```

### Needs data lookup

```bash
python3 leads/research.py needs 40701    # ZIP
python3 leads/research.py needs KY       # state summary
python3 leads/research.py status         # what's been researched
```

---

## GitHub Workflow

```
feature/candidate-<id>   ← AI opens PR from here
        ↓  PR
main                     ← requires PR + CI pass; never direct push
        ↓  on merge
GitHub Pages (_site/)    ← CI builds and deploys automatically
```

**Required CI checks before merge:**
- `validate` — schema, business rules, JS syntax, pytest
- `recompute-decision` — adversarial trust score recomputation (candidate-verification.yml)

**Branch protection** (must be set in GitHub repo settings — not enforced by code alone):
- Require PR before merge to `main`
- Required status checks: `validate`, `recompute-decision`
- No admin bypass

**PR must include**: candidate/resource IDs changed, fields changed, evidence for each, verification method, remaining uncertainty, sensitive-resource consideration.

---

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| SearXNG | `http://localhost:8888` | Web search for lead discovery (curl only) |
| LiteLLM | `http://100.73.139.50:4000/v1` | AI inference proxy |
| Census API | `https://api.census.gov` | ACS data (key in `.env`) |

Environment variables (`.env`, never commit):
- `SEARXNG_URL` — override SearXNG base URL
- `LITELLM_BASE_URL` / `LITELLM_MASTER_KEY` — LiteLLM proxy
- `CENSUS_API_KEY` — Census Bureau API key

---

## Current State

| Metric | Value |
|--------|-------|
| Published resources | **0** (clean reset; ready for first records) |
| Approved YAMLs | 0 (`source/approved/` is empty) |
| Active candidates | 0 (`source/candidates/` is empty) |
| Lead queue | Reset (`leads/dedup.json` v2, 0 discovered) |
| Expansion wave | Wave 0 complete (Laurel County KY); Wave 1 pending |
| Pilot mode | `manual_pilot` / `simulation` (all automation off) |

### Geographic Coverage

Wave 0 (done): Laurel County KY (London, ZIP 40744). 48 leads found, not yet processed into candidates.

Wave 1 (next): Knox, Whitley, Clay, Pulaski, McCreary, Rockcastle counties (all KY, bordering Laurel).

Priority ordering within any county: need_score > 60 (high) → 35–60 (moderate) → < 35 (low). Need scores in `data/census/needs-analysis.json`.

### Pilot Limits (manual_pilot.json)

- Max active cases: 1
- Max received leads: 50
- Allowed geography: Laurel County KY + 15 mi radius from London KY (37.1690, -84.0824)
- Statewide/national resources serving Laurel County are in scope
- No confidential addresses, no closures, no bulk discovery, no geographic expansion without explicit enable

---

## Key Design Decisions

- **Generated files not committed**: `data/`, `pages/`, `print/`, `_site/` rebuilt by CI on every merge. Never commit them.
- **`source/candidates/` never served**: GitHub Pages serves only `_site/` which is built from `source/approved/` only. Candidates, leads, scripts, census data are never public.
- **Trust scoring is deterministic**: CI recomputes from raw evidence; if it doesn't match the signed decision, the build fails. No agent can inflate its own score.
- **Role separation is code-enforced**: `workflow_state.py` raises `IllegalTransition` on violations. Cannot be bypassed by prompt instruction.
- **Paperclip decoupled**: Previously managed via Paperclip; now standalone. The `pilot/` tooling will be superseded by the Beacon app.
- **BASE_PATH**: `scripts/build_pages.py` has `BASE_PATH = "/beacon"` (GitHub project page path). Update if domain changes.
