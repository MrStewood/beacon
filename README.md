# Beacon

Community Resource Directory — helping people find food, shelter, healthcare, recovery, and more.

## Browse

**[View the Directory](https://mrstewood.github.io/beacon/)**

## Download

| Format | Link |
|--------|------|
| CSV (Spreadsheet) | [resources.csv](data/resources.csv) |
| JSON (Developers) | [resources.json](data/resources.json) |
| By County | [resources-by-county/](data/resources-by-county/) |
| By Need | [resources-by-need/](data/resources-by-need/) |
| By State | [resources-by-state/ky.json](data/resources-by-state/ky.json) |

## Embed on Your Site

```html
<script src="https://mrstewood.github.io/beacon/embed/widget.js"
        data-county="laurel" data-need="food" data-theme="light" data-limit="10"></script>
```

Options: `data-county`, `data-need`, `data-theme` (light/dark), `data-limit`

## Data Schema

Each resource includes:
- **Identity**: name, description, alternate names
- **Location**: address, city, state, zip, county, lat/lng
- **Contact**: phones, email, website, facebook
- **Services**: needs (what they solve), service types (how they deliver), populations (who they serve)
- **Operations**: eligibility, cost, hours, intake process, capacity, waitlist, insurance
- **Verification**: last verified date, confidence level, source URLs
- **Metadata**: first seen, notes, related resources

## Needs

food · shelter · housing · clothing · health · mental-health · addiction · crisis · documents · jobs · legal · family · transportation · education · veterans · community

## Service Types

hotline · walk-in · appointment · residential · outpatient · mobile · online · peer-led · faith-based · government

## Populations

anyone · families · women · men · youth · seniors · veterans · lgbtq+ · disability · re-entry · pregnant · substance-use

## Contribute

- [Suggest a Resource](https://github.com/MrStewood/beacon/issues/new?template=suggest-resource.md)
- [Report an Update](https://github.com/MrStewood/beacon/issues/new?template=update-resource.md)

## Data Source

Initial data from [Isaiah 58:10 Ministries & Outreach](https://is5810.com/main/resources/). Expanding to cover all of Kentucky and beyond.
