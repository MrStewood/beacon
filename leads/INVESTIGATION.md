# Beacon Lead Investigation Process

## Overview

Investigation takes a discovered lead and fills out ALL fields by researching the organization across multiple sources. This is NOT the approval step — it's deep research.

## Pipeline Position

```
Lead Generation → Investigation → Approval → Publishing
     ↓                  ↓              ↓           ↓
  leads/*.json    investigations/   human review  source/approved/
```

## Investigation Rules

### 1. Search the org's own website FIRST

```bash
# Find their website from the lead
browser_navigate("https://www.godspantry.org")
browser_snapshot()
```

Look for: Contact page, About page, Locations, Hours, Services, Eligibility, What to Bring, FAQ.

### 2. Search other resources

```bash
# SearXNG searches
curl -s "http://searxng:8080/search?q=ORG+NAME+LOCATION+PHONE&format=json"
curl -s "http://searxng:8080/search?q=ORG+NAME+hours+eligibility&format=json"
curl -s "http://searxng:8080/search?q=ORG+NAME+address+directions&format=json"
```

Check: Google Maps, Facebook, Yelp, health department directories, United Way 211, state agency listings, news articles.

### 3. Fill ALL fields

Don't stop at phone and address. Keep searching for:

| Field | Where to find it |
|---|---|
| `phones` | Website contact page, Google Maps, Facebook |
| `hours` | Website, Google Maps, Facebook "About" |
| `address` | Website, Google Maps, Waze, news articles |
| `email` | Website contact page, Facebook |
| `url` | Already have from lead |
| `description` | About page, mission statement, news articles |
| `eligibility` | Website FAQ, services page, intake info |
| `what_to_bring` | Intake requirements, FAQ, "how to get help" page |
| `cost` | Services page, FAQ |
| `service_types` | Services page, how help is delivered |
| `populations` | Who they serve, eligibility criteria |
| `languages` | Website, Google Maps listing |
| `intake_process` | How to start, appointment vs walk-in |
| `capacity` | News articles, annual reports |
| `facebook` | Search "ORG NAME facebook" |

### 4. If you can't find something

- Search variations: "ORG NAME phone number", "ORG NAME hours London KY"
- Check Google Maps listing (often has phone, hours, reviews)
- Check Facebook About page
- Check 211 / United Way directory listings
- Check state agency registries
- Check news articles about the org
- If still not found after 3 different searches, mark as `null` and note "not found in available sources"

### 5. Record NEW leads you find

During investigation you WILL find other organizations. When you do:

```bash
# Add to the leads file or create a new one
cat >> leads/results_{zip}.json << 'EOF'
{
  "name": "New Org Found During Investigation",
  "category": "...",
  ...
}
EOF
```

Or create a separate investigation note:
```json
{
  "discovered_during_investigation": [
    {"name": "...", "category": "...", "source": "found on godspantry.org/help"},
    {"name": "...", "category": "...", "source": "mentioned in health dept listing"}
  ]
}
```

### 6. Log notes on the research process

Every investigation MUST include a `notes` section:

```json
{
  "notes": {
    "research_log": [
      "2026-09-23 10:00 - SearXNG search: 33 results found",
      "2026-09-23 10:01 - Visited godspantry.org/contact: found London listed as distribution center",
      "2026-09-23 10:02 - Visited laurelcohealthdept.org: found phone 606-862-6693, hours Mon-Fri 7a-3:30p",
      "2026-09-23 10:03 - Facebook page confirms org identity (1,573 likes)",
      "2026-09-23 10:04 - Cross-referenced 3 sources, all consistent"
    ],
    "gaps_found": ["email not publicly listed", "what_to_bring not specified"],
    "confidence_notes": "Address and phone confirmed by multiple sources. Hours from health dept only.",
    "new_leads_found": ["Come-Unity Cooperative Care (found on health dept food pantry list)"]
  }
}
```

## Output Format

Save investigation to: `leads/investigations/{zip}-{org-slug}.json`

```json
{
  "lead_id": "laurel-gods-pantry-food-bank-se-kentucky",
  "investigation_date": "2026-09-23",
  "investigator": "agent-id",

  "name": "...",
  "category": "...",
  "description": "...",

  "phones": [...],
  "email": "...",
  "url": "...",
  "facebook": "...",

  "address": "...",
  "city": "...",
  "state": "...",
  "zip": "...",
  "county": "...",

  "hours": "...",
  "eligibility": "...",
  "what_to_bring": "...",
  "cost": "...",
  "service_types": [...],
  "populations": [...],
  "languages": [...],
  "intake_process": "...",

  "verification_status": "website-checked",
  "confidence": "high",
  "source_urls": [...],
  "last_verified": "2026-09-23",

  "notes": {
    "research_log": [...],
    "gaps_found": [...],
    "confidence_notes": "...",
    "new_leads_found": [...]
  },

  "status": "active"
}
```
