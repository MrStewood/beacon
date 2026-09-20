# Beacon Data Schema

## Overview

Every resource in Beacon follows a standardized JSON schema. This document describes all fields, their types, and valid values.

## Resource Record

```json
{
  "id": "string (required)",
  "name": "string (required)",
  "county": "string (required)",
  "status": "string (required)",
  "needs": ["string"],
  "service_types": ["string"],
  "populations": ["string"]
}
```

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable, URL-safe identifier. Format: `{county}-{slugified-name}` |
| `name` | string | Official organization name |
| `county` | string | Primary service county, or "Statewide" |
| `status` | enum | `active`, `needs-verification`, `closed` |

## Contact Fields

| Field | Type | Description |
|-------|------|-------------|
| `phones` | string[] | Phone numbers including short codes (988, 211) |
| `email` | string | General or intake email |
| `url` | string | Website URL (must start with http:// or https://) |
| `facebook` | string | Facebook page URL |

## Location Fields

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | Street address, or "Statewide" / "Online" |
| `city` | string | City or town |
| `state` | string | Two-letter state code (e.g., "KY") |
| `zip` | string | US zip code |
| `latitude` | number | Decimal latitude for mapping |
| `longitude` | number | Decimal longitude for mapping |
| `map_url` | string | Auto-generated Google Maps link |

## Service Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Plain English description (max 2000 chars) |
| `needs` | enum[] | What problem this resource solves |
| `service_types` | enum[] | How help is delivered |
| `populations` | enum[] | Who this resource serves |
| `eligibility` | string | Who qualifies and what is required |
| `cost` | enum | Cost to the person receiving services |
| `hours` | string | When services are available |
| `languages` | string[] | Languages in which services are available |
| `what_to_bring` | string | Documents or items to bring for intake |
| `referral_required` | boolean | Whether a referral is required |
| `intake_hours` | string | When walk-in intake is accepted |
| `intake_process` | string | How to start receiving services |
| `capacity` | string | Beds, slots, or "Unknown" |
| `waitlist` | boolean | Whether there is currently a waiting list |
| `accepts_insurance` | string[] | Insurance plans accepted |

## Verification Fields

| Field | Type | Description |
|-------|------|-------------|
| `verification_status` | enum | How thoroughly verified |
| `last_verified` | date | YYYY-MM-DD when last confirmed |
| `verified_by` | string | Agent ID, human name, or "initial-import" |
| `confidence` | enum | Data accuracy confidence level |
| `source_urls` | string[] | URLs where information was found |

## Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `first_seen` | date | When Beacon first discovered this resource |
| `alternate_names` | string[] | DBAs, abbreviations, old names |
| `tags` | string[] | Freeform tags for search |
| `notes` | string | Tips, quirks, internal notes (public) |
| `related` | string[] | IDs of same-org different-location entries |

## Enum Values

### needs
`addiction`, `clothing`, `community`, `crisis`, `documents`, `education`, `family`, `food`, `health`, `housing`, `jobs`, `legal`, `mental-health`, `shelter`, `transportation`, `veterans`

### service_types
`hotline`, `walk-in`, `appointment`, `residential`, `outpatient`, `mobile`, `online`, `peer-led`, `faith-based`, `government`

### populations
`anyone`, `families`, `women`, `men`, `youth`, `seniors`, `veterans`, `lgbtq+`, `disability`, `re-entry`, `pregnant`, `substance-use`, `recovery`

### cost
`free`, `sliding-scale`, `insurance`, `private-pay`, `unknown`

### status
`active`, `needs-verification`, `closed`

### confidence
`high` (confirmed by direct contact), `medium` (inferred from web), `low` (unverified)

### verification_status
`unverified`, `auto-inferred`, `website-checked`, `phone-confirmed`, `in-person-verified`

## JSON Schema

The full JSON Schema is at `schema/resource.schema.json`. Use it to validate your data:

```bash
python scripts/validate.py
```
