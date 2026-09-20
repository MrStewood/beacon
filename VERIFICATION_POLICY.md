# Beacon Verification Policy

Full formulas, source tiers, caps, and thresholds: see [TRUST_SCORING.md](TRUST_SCORING.md).
This file summarizes the operational rules; TRUST_SCORING.md and its enforcing
code (`scripts/trust_scoring.py`, `scripts/validate_candidate.py`) are authoritative.

Verification is **claim-level**, never one record-wide checkbox. Every
material claim carries its own evidence list and its own status: `verified`,
`verified-with-limitation`, `contradicted`, `uncertain`, `stale`,
`not-found`, `not-applicable`, or `unsafe-to-publish`. A candidate's
`verification_status`/legacy field below is a display summary computed from
claim statuses, not something an agent sets directly.

## Verification Levels (legacy display labels — derived, not authored)

| Level | Description | Evidence Required |
|-------|-------------|-------------------|
| `verified` | Direct confirmation from provider | Phone call, email, or in-person |
| `website-checked` | Official website confirmed | URL response + content match |
| `source-only` | From published directory | Source URL + date |
| `needs-review` | Requires verification | None yet |
| `reported-closed` | Closure reported | Evidence of closure |

## Acceptable Evidence

### Primary Sources (High Confidence)
- Official provider website
- Government directory listing
- Direct phone confirmation
- Email confirmation
- In-person verification

### Secondary Sources (Medium Confidence)
- 211 directory listing
- Nonprofit directory (GuideStar, etc.)
- Licensed provider directory
- News article about the organization

### Discovery Sources (Low Confidence - do not publish on)
- Search engine results
- AI-generated summaries
- Map listings without verification
- Social media posts
- Third-party mentions

## Verification Rules

1. Every material field change must have supporting evidence
2. Search snippets are discovery-only, not evidence
3. AI content is never evidence
4. Map listings alone do not prove a provider is active
5. High-risk records need official source or two independent sources
6. Unknown information must remain unknown
7. Do not mark closed based on one broken website
8. Do not mark closed based on one unanswered call

## Verification Expiration

- `verified`: Reverify annually
- `website-checked`: Reverify every 6 months
- `source-only`: Reverify quarterly
- `needs-review`: Prioritize for verification

## Sensitive Resource Verification

Sensitive resources (crisis, DV, children, medical) require:
- Official provider source OR
- Two independent reputable sources
- Human approval before publication

## Enforcement

None of the above is voluntary. Every candidate under `source/candidates/**`
is validated by `scripts/validate_candidate.py`, which independently
recomputes claim/record scores and the publication decision and compares
them to the signed `decision` block in the file. `.github/workflows/candidate-verification.yml`
runs this as a required branch-protection check on `main` — a PR cannot merge
if the recomputed decision disagrees with the committed one, or if a
quarantined candidate has reached `pr-opened` or later. See TRUST_SCORING.md.
