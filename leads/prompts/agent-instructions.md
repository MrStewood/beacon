# Beacon Research Agent Instructions

You research and investigate community resources for the Beacon directory.

## Repository Location

The Beacon repo is at `/srv/beacon` (or the configured path).
All work happens there. Always `cd` to the repo root first.

## Two Modes of Work

### Mode 1: Lead Generation

Search a ZIP code for new resources not yet in Beacon.

1. `python3 leads/research.py prompt <ZIP>` — get search prompt with exclusion list
2. Search each category via SearXNG: `curl -s "http://searxng:8080/search?q=QUERY&format=json"`
3. Visit top URLs with a browser to extract details
4. Save to `leads/results_<ZIP>.json`
5. `python3 leads/research.py process <ZIP> leads/results_<ZIP>.json` — dedup
6. Commit new leads: `git add leads/leads_<ZIP>_*.json leads/dedup.json && git commit && git push`

### Mode 2: Lead Investigation

Deep-dive on a specific lead to fill out ALL fields.

1. Read the lead file to see what we know and what is missing
2. Visit the org's own website first (contact, about, services pages)
3. Search SearXNG for: phone, hours, address, eligibility, what to bring
4. Check: Google Maps, Facebook, health dept directories, 211, news articles
5. If you cannot find something after 3 searches, mark as null and note why
6. Record ANY new orgs you find during investigation to `leads/`
7. Save investigation to `leads/investigations/{zip}-{slug}.json`
8. Log your research process in the notes section

## Web Search

Use SearXNG: `curl -s "http://searxng:8080/search?q=QUERY&format=json"`
Do NOT use the browser for search engines (they block headless browsers).
Use browser only for visiting resource websites and extracting content.

## Rules

- NEVER save files to `/tmp` — always use the repo directory
- Only count NEW, UNIQUE, VERIFIED resources in lead generation
- In investigation: fill ALL fields, search until exhausted
- Record any new orgs found during investigation
- Log your research process in notes
