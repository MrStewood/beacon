# Research ZIP {{zip_code}}

Lead generation: research community resources in the given ZIP code.

## Steps

1. Run: `python3 leads/research.py prompt {{zip_code}}`
   The output contains a search prompt covering all 17 Beacon categories with the existing resource exclusion list.
2. Feed the prompt to a web-search agent or run the searches yourself.
3. Collect findings as structured JSON matching the schema in the prompt.
4. Save results to a file (e.g. `leads/results_{{zip_code}}.json`).
5. Run: `python3 leads/research.py process {{zip_code}} leads/results_{{zip_code}}.json`
   This deduplicates against existing Beacon data and previously discovered leads.
6. New leads are saved to `leads/leads_{{zip_code}}_YYYY-MM-DD.json`.
7. Resources found outside the target ZIP are flagged in `leads/dedup.json` under `out_of_area`.

## Rules

- Never fabricate phone numbers, addresses, or service details.
- Use null/unknown when facts cannot be established.
- Do not report resources already in Beacon (the exclusion list handles this).
- Each resource must include source URLs.
- Mark all findings as `verification_status: unverified`, `confidence: medium`.
- Write a 1-line summary comment on the issue when done: how many found, how many new, how many duplicates, how many out-of-area.
