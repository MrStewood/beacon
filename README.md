# Beacon

Community Resource Directory — helping people find food, shelter, healthcare, recovery, and more.

**[View the Directory](https://mrstewood.github.io/beacon/)**

## Quick Start

### Browse
Visit https://mrstewood.github.io/beacon/ to search resources by need, location, or service type.

### Download
| Format | Link |
|--------|------|
| CSV (Spreadsheet) | [resources.csv](data/resources.csv) |
| JSON (Full) | [resources.json](data/resources.json) |
| JSON (Compact) | [index.json](data/index.json) |
| By County | [resources-by-county/](data/resources-by-county/) |
| By Need | [resources-by-need/](data/resources-by-need/) |

### Embed
```html
<script src="https://mrstewood.github.io/beacon/embed/widget.js"
        data-county="laurel" data-need="food" data-theme="light" data-limit="10"></script>
```

## Development

### Prerequisites
- Python 3.10+
- pip install jsonschema pytest

### Local Development
```bash
# Clone the repo
git clone git@github.com:MrStewood/beacon.git
cd beacon

# Validate data
python scripts/validate.py

# Run tests
pytest tests/ -v

# Serve locally
python -m http.server 8000
# Open http://localhost:8000
```

### Data Pipeline
Canonical resource data lives in `source/approved/**/*.yaml`. The build generates:
- `data/resources.json` — public dataset
- `data/resources.csv` — spreadsheet export
- `data/index.json` — lightweight search index

```bash
# Regenerate all data
python scripts/build.py

# Validate
python scripts/validate.py
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_crisis.py -v
pytest tests/test_schema.py -v
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

To suggest a resource or report an error, open an issue using our templates:
- [Suggest a Resource](https://github.com/MrStewood/beacon/issues/new?template=suggest-resource.md)
- [Report a Correction](https://github.com/MrStewood/beacon/issues/new?template=update-resource.md)

## License

- **Code**: MIT License (see [LICENSE](LICENSE))
- **Data**: CC BY 4.0 (see [LICENSE](LICENSE))

## Disclaimer

Resource data may contain errors or outdated information. Always verify hours, eligibility, availability, and intake requirements directly with the provider. Beacon is not affiliated with any listed organization.
