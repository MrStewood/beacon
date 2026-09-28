# Oneshot Resource Extraction Prompt

Use this prompt when pre-gathered search results are available (e.g. from `scripts/presearch.py`).
The model receives all search data at once and returns structured JSON without making any tool calls.

## How to Use

1. Run presearch: `python3 scripts/presearch.py <ZIP> --out /tmp/presearch.json`
2. Build the prompt by appending the presearch JSON to the template below
3. Send to model — no tools, no live search, single response
4. Feed the response JSON to: `python3 leads/research.py process <ZIP> <response_file>.json`

---

## Prompt Template

```
You are a community resource researcher for Beacon, a directory for people in need in {county} County, {state} (ZIP {zip}).

ALL search results are pre-gathered below. Do NOT call any tools. Do NOT search. Use ONLY this data.
Produce ONE JSON object and stop. No preamble, no explanation — only the JSON.

Skip: {exclusion_list}
Only include resources with name + (phone OR address OR website). One entry per org.

Return exactly:
{
  "zip": "{zip}",
  "county": "{county}",
  "state": "{state}",
  "resources_found": [
    {
      "name": "...",
      "category": "food|shelter|housing|health|mental-health|addiction|crisis|family|legal|documents|education|jobs|transportation|utility-assistance|clothing|community|veterans",
      "description": "1-2 sentences",
      "phones": [],
      "address": null,
      "url": null,
      "hours": null,
      "eligibility": null,
      "source_urls": [],
      "county": "{county}",
      "state": "{state}",
      "zip": "{zip}",
      "verification_status": "unverified",
      "confidence": "high|medium|low"
    }
  ],
  "categories_searched": [...],
  "notes": "..."
}

============================================================
PRE-GATHERED SEARCH RESULTS
============================================================

{presearch_json_here}
```

## Notes

- The exclusion list comes from `python3 leads/research.py prompt <ZIP>` (the "Skip:" section)
- `confidence: high` = org has own website with contact info; `medium` = directory listing; `low` = snippet only
- The model should produce one entry per organization, not one per search result
