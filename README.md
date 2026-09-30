# Beacon

Community Resource Directory — helping people find food, shelter, healthcare, recovery, and more.

**[View the Directory](https://mrstewood.github.io/beacon/)**

## How This Works

```
source/candidates/    ← research writes candidate YAMLs on main
        ↓  (CI validates trust scores on push; human authorizes publication)
source/approved/      ← canonical published records
        ↓  (CI builds on push to main)
_site/                ← public website deployed to GitHub Pages
```

Only records in `source/approved/` appear on the public site.
Candidates, leads, scripts, and operational data are never served publicly.

## Browse

Visit https://mrstewood.github.io/beacon/ to search resources by need, location, or service type.

## Download

| Format | Link |
|--------|------|
| CSV (Spreadsheet) | [resources.csv](data/resources.csv) |
| JSON (Full) | [resources.json](data/resources.json) |
| JSON (Compact) | [index.json](data/index.json) |

## Embed

```html
<script src="https://mrstewood.github.io/beacon/embed/widget.js"
        data-county="laurel" data-need="food" data-theme="light" data-limit="10"></script>
```

## Development

### Prerequisites

- Python 3.10+
- `pip install jsonschema pyyaml pytest`

### Local Build

```bash
# Validate + build everything → _site/
python3 scripts/build.py

# Build + run tests
python3 scripts/build.py --test

# Validate only (no build)
python3 scripts/validate.py

# Serve locally
python3 -m http.server 8000 --directory _site
# Open http://localhost:8000
```

### Repository Layout

```
source/
  approved/         ← canonical published records (YAML) — build reads only here
  candidates/       ← in-progress candidates with claim/evidence metadata

operations/         ← n8n scheduling configuration and individual lead records
leads/              ← historical discovery observations and evidence

scripts/            ← build, validation, geocoding, trust scoring
tests/              ← test suite
schema/             ← JSON schemas for resources and candidates

assets/             ← CSS, JS, images (static)
embed/              ← embeddable widget
index.html          ← public search interface
organizations.html  ← organization portal

data/               ← GITIGNORED generated JSON/CSV outputs
pages/              ← GITIGNORED generated resource/county/need HTML
print/              ← GITIGNORED generated print guides
_site/              ← GITIGNORED complete built site (deployed to GitHub Pages)
```

### Data Pipeline

Canonical resource data lives in `source/approved/**/*.yaml`.
Public data in `data/` is currently committed and checked against approved YAML.
Use the official build to regenerate it; never edit it manually. Pages and `_site/` are generated.

[n8n operating rules](AGENTS.md) and [queue layout](operations/README.md) govern automation.

### Adding a Resource

1. AI agent researches lead → writes `source/candidates/<county>/<id>.yaml` on `main`
2. Push → CI runs schema validation + trust score recomputation
3. Human authorizes promotion into `source/approved/`
4. Push of approved + generated data → CI builds the site and deploys to GitHub Pages

### Testing

```bash
pytest tests/ -v                    # full suite
pytest tests/test_crisis.py -v      # crisis resource checks
pytest tests/test_trust_scoring.py -v  # trust scoring invariants
```

## Data Schema

See [schema/resource.schema.json](schema/resource.schema.json) for the full JSON Schema.

Key fields:
- **needs**: food, shelter, housing, clothing, health, mental-health, addiction, crisis, documents, jobs, legal, family, transportation, education, veterans, community
- **service_types**: hotline, walk-in, appointment, residential, outpatient, mobile, online, peer-led, faith-based, government
- **populations**: anyone, families, women, men, youth, seniors, veterans, lgbtq+, disability, re-entry, pregnant, substance-use, recovery
- **confidence**: high (confirmed), medium (inferred from web), low (unverified)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

To suggest a resource or report an error, open an issue:
- [Suggest a Resource](https://github.com/MrStewood/beacon/issues/new?template=suggest-resource.md)
- [Report a Correction](https://github.com/MrStewood/beacon/issues/new?template=update-resource.md)

## License

- **Code**: MIT License
- **Data**: CC BY 4.0

See [LICENSE](LICENSE).

## Disclaimer

Resource data may contain errors or outdated information. Always verify hours, eligibility, availability, and intake requirements directly with the provider. Beacon is not affiliated with any listed organization.
