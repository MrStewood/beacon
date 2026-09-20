# Beacon Schema v3 Migration

## Overview

Schema v3 introduces structured geographic modeling to support nationwide expansion.

## Key Changes

### 1. Structured Locations

**v2:** Single `address` field, no coordinates
**v3:** `locations[]` array with structured address, FIPS codes, geocoding status

```json
{
  "locations": [{
    "id": "lexington-office",
    "location_type": "physical",
    "address_line_1": "123 Main St",
    "city": "Lexington",
    "county_name": "Fayette",
    "county_fips": "21067",
    "state": "KY",
    "postal_code": "40507",
    "latitude": 38.0406,
    "longitude": -84.5037,
    "geocoding_status": "verified",
    "publicly_displayed": true
  }]
}
```

### 2. Service Coverage

**v2:** `county` field (conflated location with service area)
**v3:** Separate `coverage_scope` + `service_areas[]`

```json
{
  "coverage_scope": "multi-county",
  "service_areas": [{
    "type": "county",
    "state": "KY",
    "values": [
      {"name": "Fayette", "fips": "21067"},
      {"name": "Jessamine", "fips": "21113"}
    ]
  }],
  "states_served": ["KY"]
}
```

### 3. Coverage Scopes

| Scope | Description |
|-------|-------------|
| `national` | Available nationwide |
| `state` | Available in one state |
| `county` | Available in one county |
| `multi-county` | Available in multiple counties |
| `online` | Available online |

### 4. Stable IDs

**v2:** `{county}-{name-slug}` (changes if county changes)
**v3:** `{org-name-slug}` (stable) + `legacy_ids[]` for backward compatibility

### 5. Resource Types

New `resource_type` field classifies organizations:
- `direct-provider` — Provides services directly
- `hotline` — Phone/text support
- `government` — Government agency
- `community-program` — Community-based

## Migration Results

| Metric | Count |
|--------|-------|
| Total resources | 218 |
| Successfully migrated | 218 |
| Missing physical location | 109 |
| Statewide coverage | 111 |
| County coverage | 107 |

## Backward Compatibility

- Deprecated fields (`county`, `address`, `city`, `state`, `zip`) are preserved
- Existing URLs continue working
- v2 API endpoints remain available
- Legacy IDs stored in `legacy_ids[]` array

## Next Steps

1. Add geocoding for physical addresses
2. Migrate existing URLs to use stable IDs
3. Add state-specific pages
4. Implement location search
