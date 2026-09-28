# Investigate Lead {{zip_code}} {{org_name}}

Deep investigation of a discovered lead. Fill out ALL fields by searching the org website,
government directories, Google Maps, Facebook, news articles, and other resources.

## Steps

1. `cd /path/to/beacon`
2. Read the lead from `leads/leads_{{zip_code}}_*.json`
3. Visit the org's own website (contact, about, services pages)
4. Search SearXNG for phone, hours, address, eligibility, what to bring
5. Check Google Maps, Facebook, health dept directories, 211, news articles
6. If you cannot find something after 3 searches, mark as null and note why
7. Record ANY new orgs found during investigation to `leads/`
8. Save to `leads/investigations/{{zip_code}}-{{org_slug}}.json`
9. Log research process in the notes section

## Output Format

See `leads/INVESTIGATION.md` for the full investigation JSON schema.

## Rules

- Search the org's own website first
- Fill ALL fields; do not leave blanks if the info exists somewhere
- If you find other orgs during research, add them as new leads
- Log every search you do in the `notes.research_log` array
- Set `verification_status` based on how many sources confirmed each fact
