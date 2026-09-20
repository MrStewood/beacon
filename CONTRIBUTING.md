# Contributing to Beacon

Thank you for helping maintain this community resource directory. Your contributions help people find the support they need.

## How to Contribute

### Suggest a New Resource

1. Go to [Issues](https://github.com/MrStewood/beacon/issues/new?template=suggest-resource.md)
2. Fill in the resource information
3. Submit the issue

### Report Incorrect Information

1. Go to [Issues](https://github.com/MrStewood/beacon/issues/new?template=update-resource.md)
2. Identify the resource and what needs updating
3. Submit the issue

### Data Quality

If you notice a resource with wrong phone numbers, closed status, or other data issues, please open an issue with:
- Resource name
- What's incorrect
- Correct information (if you have it)

## Development

### Setup

```bash
git clone git@github.com:MrStewood/beacon.git
cd beacon
pip install jsonschema pytest
```

### Making Changes

1. Fork the repository
2. Create a branch for your changes
3. Make your edits
4. Run tests: `pytest tests/ -v`
5. Run validation: `python scripts/validate.py`
6. Submit a pull request

### Data Changes

Source data is in `source/raw/kentucky.csv`. To add or update resources:

1. Edit the CSV file
2. Run the build: `python scripts/build.py`
3. Verify the output in `data/resources.json`
4. Commit both the source CSV and generated files

### Schema Changes

If you need to add new fields:

1. Update `schema/resource.schema.json`
2. Update `schema/categories.json` if adding new categories
3. Update `scripts/parse_resources.py` to populate the new field
4. Update `index.html` to display the new field
5. Add tests for the new field

## Code Style

- Python: Follow PEP 8
- JavaScript: Use const/let, not var
- HTML: Use semantic elements
- CSS: Use CSS variables for colors

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_crisis.py -v

# Run validation
python scripts/validate.py
```

## Questions?

Open a [Discussion](https://github.com/MrStewood/beacon/discussions) for questions about contributing.
