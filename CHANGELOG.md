# Direct-to-main workflow — 2026-09-30

Repository process no longer requires pull requests. Maintainers and authorized automation commit and push directly to `main`. Human authorization is still required before promoting records into `source/approved/`. CI continues to validate on push.

# n8n migration — 2026-09-30

Migrated 86 discovery entries to stable individual lead records under operations/leads/. Added scheduling configuration, queue schemas, candidate lead links, and validation tests. Retired Python/Paperclip orchestration and old queue registries. Preserved approved records and evidence history. Unified operating policies around n8n and human-approved publication. Public-data/CI migration remains separate.

# Changelog

All notable changes to Beacon are documented here.

## Unreleased — Loop Error Visibility (2026-09-29)

- Fixed `NameError: datetime is not defined` — the geography-gates import edit
  had dropped `from datetime import datetime, timezone`, so any review decision
  that hit `_do_requeue`/`_utc_now` crashed the loop's review step
- Dashboard mode now captures subprocess output instead of letting it race the
  screen redraw (child stack traces used to flash for one frame and vanish)
- Step output and in-process exceptions are persisted to `leads/runs/loop.log`;
  a step exception shows the traceback in the messages pane and stops the loop
  with a pointer to the log instead of crashing silently
- Fixed a build→review→escalate livelock: investigations whose candidate sat in
  `leads/needs_human_review/` were still counted as "needs candidate", so the
  loop rebuilt and re-escalated them every step forever — escalated candidates
  now count as done, `build_candidate` refuses to rebuild them, and the
  dashboard/status show a "Needs human review" count and focus line
- Loop dashboard now stays alive during long steps: a `▶ action → target`
  start line plus a 15-second "still working" heartbeat re-renders the pane
  (steps used to freeze the screen with no feedback, looking hung)
- Step subprocesses run in their own session (`start_new_session`), so the
  supervisor's Ctrl+C no longer SIGINTs the investigation child and kills its
  Playwright driver mid-run — the first Ctrl+C now genuinely "finishes the
  current step" as the message promises
- Added `tests/test_pipeline_state.py` regression coverage

## Unreleased — Geography Publication Gates (2026-09-29)

- `scripts/geocode.py` now splits venue names and embedded city/state/ZIP values
  out of `address_line_1`, preferring the verified embedded ZIP over the lead ZIP
- Auto-approval geocodes every public physical address before writing
  `source/approved/`; an address that cannot be geocoded returns the candidate
  to `needs_more_research`
- Local active services must carry explicit `service_areas`; approval derives
  them from `coverage_scope`/location when possible and otherwise blocks
- `scripts/validate_sources.py` now fails CI when approved local records lack
  service areas or public physical locations lack coordinates
- Added `tests/test_geography_gates.py`; corrected and geocoded Calvary Baptist
  Food Pantry and London KY Warming Center records
- Detail drawer now links to the full resource page with its coverage map
  (`Full page with coverage map →`)

## Unreleased — Pipeline Supervisor CLI (2026-09-28)

- `app/pipeline/dashboard.py` — readable single-screen CLI dashboard (requires
  `rich`): watch-mode essentials only, low-border layout, clear current focus,
  health line, progress bars, small queue preview, and width/height-safe
  truncation instead of dense full-catalog tables
- `supervisor --dashboard` renders the dashboard once and exits; output is
  capped to the terminal height so fullscreen watch mode never requires scrollback
- `supervisor --loop` runs continuously, re-rendering a stable top dashboard
  while step output accumulates in a bounded bottom messages pane; dashboard
  mode suppresses the plain-text decision banner and stops itself on `idle` or
  `alert_human`
- Ctrl+C once = finish current step and stop cleanly; Ctrl+C again = force quit
- `_read_leads` now tracks `by_cat_status` (queued/investigated per category)
- Rejected record cleanup: God's Pantry London is explicitly marked
  `workflow_state: rejected` / `public_access: no` because the London site is
  a regional distribution center/warehouse, not public-facing direct service
- Dashboard now treats reviewed approvals in `leads/rejected/` as resolved
  rejections instead of publish-missing health flags
- `beacon-supervisor.timer` disabled — loop mode is started manually

## Unreleased — Repo Restructuring (2026-09-27)

### GitHub Pages — serve only public content
- Changed Pages artifact from repo root (`.`) to `_site/` directory
- `scripts/build.py` now assembles `_site/` containing only: `index.html`,
  `organizations.html`, `assets/`, `embed/`, `schema/`, `data/` (public JSON/CSV),
  `pages/`, `print/`, `sitemap.xml`, `robots.txt`
- `data/census/` excluded from `_site/` — operational AI reference data (35 MB),
  not part of the public web interface
- Operational directories (`leads/`, `pilot/`, `source/candidates/`, `scripts/`,
  `tests/`) never served publicly
- Fixed GitHub Actions permissions: `pages: write` / `id-token: write` moved to
  `deploy` job where `actions/deploy-pages` actually runs
- Removed `git diff --exit-code` check on generated files (they are no longer committed)

### Generated outputs — gitignored, built by CI
- `data/resources.json`, `data/resources.csv`, `data/index.json`,
  `data/catalog.json`, `data/change-report.json`, `data/v3/` removed from git tracking
- `pages/`, `print/`, `_site/` added to `.gitignore`
- AI runtime state directories (`leads/runs/`, `leads/investigations/`,
  `pilot/cases/`, `pilot/audit/`, `pilot/rejected/`) added to `.gitignore`

### source/ directory structure
- `source/approved/` — canonical published records (YAML); the only content that
  appears on the public site; populated via human-approved PRs
- `source/candidates/` — in-progress candidates; CI validates trust scores;
  never served publicly; promoted to `source/approved/` on merge

### Data reset
- Backed up and cleared prior resource records for clean restart
- Removed embedded legacy resource list; build reads only `source/approved/`

## [2.1.0] - 2026-09-20

### Phase 7: Documentation, SEO, Releases
- Add comprehensive documentation (DATA_SCHEMA, API, EMBEDDING, SECURITY)
- Add CHANGELOG
- Add GitHub release workflow
- Add version tagging to build pipeline

## [2.0.0] - 2026-09-20

### Phase 6: Print/PDF System
- Generate 20 county-specific print pages
- Generate 15 need-specific print pages
- Add QR codes linking to live directory
- Add print-specific CSS with page breaks
- Add large-print accessibility support

### Phase 5: Organization Portal
- Create organizations.html with tools for nonprofits
- Dataset download builder (CSV, JSON, GeoJSON)
- Widget configurator with live preview
- API documentation with examples
- Licensing and attribution guidance

### Phase 4: Resource Pages
- Generate 218 individual resource pages
- Add JSON-LD structured data
- Add OpenGraph social sharing metadata
- Add breadcrumb navigation
- Generate 20 county landing pages
- Generate 15 need landing pages

### Phase 3: Search Redesign
- Add synonym matching (shelter↔housing, food↔hungry)
- Add fuzzy matching for typos
- Add advanced filters (cost, language, verification, referral)
- Add sorting (relevance, A-Z, county)
- Add pagination (25 per page)
- Add compact vs detailed view toggle
- Add direct action buttons (Call, Website, Directions, Report)
- Add zero-results emergency guidance

### Phase 2: Data Pipeline
- Create build.py single entry point
- Create config.py for shared constants
- Extract JS constants to assets/js/config.js
- Add emergency banner with 911/988/211
- Add clear filters button
- Add URL state preservation (shareable searches)
- Add CONTRIBUTING.md

### Phase 1: Schema & Validation
- Add JSON Schema for resource records
- Add categories.json with canonical definitions
- Add counties.json geographic mapping
- Fix 988 crisis hotline missing phone number
- Fix XSS vulnerability in widget
- Add rel="noopener noreferrer" to external links
- Add validate.py with business rules
- Add test_crisis.py for 988/211
- Add test_schema.py for validation
- Add GitHub Actions workflow
- Add LICENSE (MIT + CC BY 4.0)

## [1.0.0] - 2026-09-20

### Initial Release
- Searchable resource directory
- 218 resources across 20 Kentucky counties
- JSON and CSV downloads
- Embeddable widget
- Print view
- GitHub Pages deployment
