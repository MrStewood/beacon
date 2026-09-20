# Beacon API Documentation

## Overview

Beacon provides static JSON endpoints for accessing resource data. No authentication required.

## Base URL

```
https://mrstewood.github.io/beacon
```

## Endpoints

### Full Dataset

```
GET /data/resources.json
```

Returns all resources with complete fields.

**Response:**
```json
{
  "metadata": {
    "version": "2.0.0",
    "last_updated": "2026-09-20",
    "total_resources": 218,
    "regions": { "KY": ["Bell", "Clark", ...] },
    "needs": ["addiction", "food", ...],
    "service_types": ["hotline", "walk-in", ...],
    "populations": ["anyone", "families", ...]
  },
  "resources": [...]
}
```

### Compact Index

```
GET /data/index.json
```

Lightweight index with essential fields only. Fast to load, good for search.

**Fields:** `id`, `name`, `county`, `city`, `needs`, `phones`, `address`, `status`, `confidence`

### County Filter

```
GET /data/resources-by-county/{county}.json
```

Resources for a specific county (lowercase, e.g., `knox`, `laurel`).

### Need Filter

```
GET /data/resources-by-need/{need}.json
```

Resources for a specific need (e.g., `food`, `shelter`, `crisis`).

### CSV Export

```
GET /data/resources.csv
```

CSV format with all fields. Good for spreadsheets.

## Query Parameters

None — filter by choosing the appropriate endpoint.

## Example Requests

### JavaScript
```javascript
// Fetch all resources
const response = await fetch('https://mrstewood.github.io/beacon/data/resources.json');
const data = await response.json();

// Filter for food resources in Knox County
const food = data.resources.filter(r =>
  r.needs.includes('food') && r.county === 'Knox'
);
```

### Python
```python
import requests

response = requests.get('https://mrstewood.github.io/beacon/data/resources.json')
data = response.json()

# Get all crisis resources
crisis = [r for r in data['resources'] if 'crisis' in r['needs']]
```

### cURL
```bash
# Get Knox County resources
curl https://mrstewood.github.io/beacon/data/resources-by-county/knox.json

# Get all food resources
curl https://mrstewood.github.io/beacon/data/resources-by-need/food.json
```

## Rate Limits

None — static files served by GitHub Pages.

## Versioning

Data is versioned via GitHub Releases. Use tagged URLs for stable references:

```
https://mrstewood.github.io/beacon/data/v2.0.0/resources.json
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
