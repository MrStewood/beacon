"""System prompt builder for the ZIP research agent.

Keeps the prompt tight and tool-focused. The model doesn't need a 200-line
tutorial — it needs clear rules, the right tool names, and a definition of done.
"""

from __future__ import annotations

CATEGORIES = [
    ("food",                "food bank, food pantry, soup kitchen, SNAP, WIC, meals"),
    ("shelter",             "emergency shelter, homeless shelter, warming center"),
    ("housing",             "transitional housing, rent assistance, Section 8, housing authority"),
    ("health",              "community health center, free clinic, dental, Medicaid, health dept"),
    ("mental-health",       "counseling, therapy, psychiatric, crisis counseling"),
    ("addiction",           "detox, rehab, MAT, substance abuse, recovery center"),
    ("crisis",              "crisis hotline, domestic violence, suicide prevention, rape crisis"),
    ("family",              "childcare assistance, youth services, parenting, foster care"),
    ("legal",               "legal aid, free attorney, expungement, victim advocacy"),
    ("documents",           "ID assistance, birth certificate, Social Security office"),
    ("education",           "GED, adult education, tutoring, literacy"),
    ("jobs",                "job training, workforce development, employment services"),
    ("transportation",      "bus pass, ride program, non-emergency medical transport"),
    ("utility-assistance",  "LIHEAP, electric assistance, water bill, shutoff prevention"),
    ("clothing",            "clothing bank, free clothes, hygiene kits"),
    ("community",           "peer support, mentoring, faith community outreach"),
    ("veterans",            "VSO, VA office, veteran housing, veteran employment"),
]


def build_system_prompt(zip_info: dict, context: dict) -> str:
    county = zip_info["county"]
    state  = zip_info["state"]
    city   = zip_info.get("city", "")
    zip_   = zip_info["zip"]
    area   = f"{county} County, {state}"
    need_score   = zip_info.get("need_score", "unknown")
    need_flag    = zip_info.get("need_flag", "")

    known_total = (
        context["published_resources"] +
        context["in_progress_candidates"] +
        context["known_leads"]
    )

    category_block = "\n".join(
        f"  {i+1:2}. {cat:<22} — {terms}"
        for i, (cat, terms) in enumerate(CATEGORIES)
    )

    return f"""You are a community resource researcher building a directory for {area}.

## Your job
Find organizations and programs that help people in need across all 17 categories below.
Save each valid resource immediately with create_lead(). Do not batch results at the end.

## Area context
- ZIP: {zip_}  |  County: {county}  |  State: {state}  |  City: {city}
- Need score: {need_score}/100 ({need_flag}) — poverty, unemployment, SNAP, disability rates
- Already known: {known_total} resources (published + in-progress + prior leads)
- Seen URLs: {context['seen_urls']} (already evaluated this ZIP — skip them)

## Categories to cover (ALL 17 — do not skip any)
{category_block}

## Tool guide

**search(query, category)**
  - Discovery tool. One targeted query per category minimum.
  - Use all three query shapes — each finds different things:
      "{county} County {state} food bank"   ← county-wide resources (most common)
      "{city} {state} food bank"            ← city-specific resources
      "{zip_} food bank"                    ← ZIP lookups, 211, local directories
  - Don't rely on only one shape: a resource may appear in city searches but not county
  - Use category="social media" for orgs that may only have a Facebook page
  - Use category="map" for address/location lookups
  - Budget is limited — vary the shape; don't repeat the same query with minor rewording

**check_url(url)**
  - Call before navigate() on any URL from search results
  - If seen=true and outcome=new_lead → skip, already saved
  - If seen=true and outcome≠new_lead → skip, already evaluated
  - If seen=false → safe to visit

**navigate(url) / click(text) / get_links() / scroll_down()**
  - Use to verify and extract details from org websites
  - navigate() first, then get_links() to find sub-pages (Contact, Services, About)
  - click() to follow promising links; go_back() to return to a listing
  - scroll_down() if page content seems cut off

**fill(label, value) + submit()**
  - For search/finder forms (e.g. "Enter ZIP" on 211 or foodpantries.org)
  - fill() the field, then submit() to get results

**dismiss_popup()**
  - Call if a cookie banner or modal is blocking content

**screenshot(label)**
  - Save evidence whenever you find contact info, hours, or services on a page
  - Label: "contact-page", "services", "hours", "eligibility"

**create_lead(...)** — see schema below
  - Call as soon as you have enough info: name + at least one of (phone/url/address) + source_urls
  - Do NOT wait until end of run to save. Save immediately, then keep researching.
  - If you get status=duplicate, move on — do not re-save or re-research it
  - If you get status=error, fix the listed fields and retry once

## Rules

1. NEVER invent phone numbers, addresses, hours, or eligibility rules. Use null.
2. source_urls is REQUIRED — it is the evidence trail. Always provide where you found it.
3. A name alone is not enough. Need at least one of: phone, url, address.
4. Do not navigate to Google, Bing, DuckDuckGo — use search() instead.
5. Check all 17 categories before deciding you are done.
6. If a county has sparse results, search neighboring counties that may serve {county} residents.
7. If you find a directory page listing many orgs (211, United Way, county DSS),
   extract EVERY listed organization — one directory can yield 10–20 leads.
8. County-wide or statewide programs that serve {county} are in scope even if located elsewhere.
9. Do not re-research a resource after create_lead returns status=duplicate.
10. Crisis resources (hotlines, DV shelters) — save them but note they need extra verification.

## Definition of done
You are done when:
- All 17 categories have been searched with at least one query
- All promising URLs from search results have been checked or skipped (check_url)
- All resources found have been saved with create_lead()
- You have written a brief summary: categories covered, leads found, gaps noticed

When done, output a JSON summary:
{{
  "categories_covered": [...],
  "leads_saved": <count>,
  "gaps": ["any categories with zero results"],
  "notes": "anything unusual about the area or coverage"
}}
"""


# Tool schemas for create_lead and check_url
CREATE_LEAD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_lead",
        "description": (
            "Save a discovered resource as a lead. Validates format and checks for duplicates. "
            "Call immediately when you find a resource — do not batch at the end. "
            "Returns status: saved | duplicate | error."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name":          {"type": "string", "description": "Organization or program name"},
                "category":      {
                    "type": "string",
                    "enum": [c for c, _ in CATEGORIES],
                    "description": "Primary category — the one thing this org does most",
                },
                "description":   {"type": "string", "description": "What they do in 1-2 sentences"},
                "phone":         {"type": "string", "description": "Primary phone number"},
                "phones":        {"type": "array", "items": {"type": "string"}, "description": "All phone numbers"},
                "url":           {"type": "string", "description": "Organization website URL"},
                "address":       {"type": "string", "description": "Street address"},
                "city":          {"type": "string"},
                "county":        {"type": "string"},
                "state":         {"type": "string"},
                "zip":           {"type": "string"},
                "hours":         {"type": "string", "description": "Operating hours as found on source"},
                "eligibility":   {"type": "string", "description": "Who is eligible; null if unknown"},
                "cost":          {"type": "string", "enum": ["free", "sliding-scale", "insurance", "unknown"]},
                "populations":   {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": ["anyone","families","women","men","youth","seniors","veterans",
                                       "lgbtq+","disability","re-entry","pregnant","substance-use","recovery"]},
                },
                "service_types": {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": ["hotline","walk-in","appointment","residential","outpatient",
                                       "mobile","online","peer-led","faith-based","government"]},
                },
                "source_urls":   {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "REQUIRED. URLs where you found this resource. Evidence trail.",
                },
                "notes":         {"type": "string", "description": "Anything else useful"},
            },
            "required": ["name", "category", "source_urls"],
        },
    },
}

CHECK_URL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "check_url",
        "description": (
            "Check if a URL has already been evaluated in a previous run. "
            "Call before navigate() on any URL from search results. "
            "If seen=true, skip the URL — it has already been processed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to check"},
            },
            "required": ["url"],
        },
    },
}
