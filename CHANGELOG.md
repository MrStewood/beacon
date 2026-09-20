# Changelog

All notable changes to Beacon are documented here.

## Unreleased

- Back up and clear existing resource records, development candidates, legacy imports, and generated resource outputs for a clean local restart.
- Build from canonical YAML instead of the embedded legacy resource list; remove that obsolete importer.
- Resolve CSV paths relative to the repository and support empty page/print generation.
- Keep required crisis-resource validation intact: an empty data set is not a deployable release.

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
