# Beacon Trust Scoring & Verification Policy

This document is the single source of truth for how a lead becomes a
published record. It is implemented, not just described: every rule below
has a corresponding function in `scripts/trust_scoring.py`, a legal edge in
`scripts/workflow_state.py`, a check in `scripts/validate_candidate.py`, and
an adversarial test in `tests/test_trust_scoring.py`. If this document and
the code ever disagree, the code (and its passing tests) is what actually
ran — file a correction to this document.

A trust score is **not** a probability that information is true. It is a
policy-based evidence-quality score: it tells you which rules the evidence
satisfied, not how confident to feel.

## Definitions

| Term | Meaning |
|---|---|
| Lead | An unverified suggestion a resource may exist or need to change. Never publishable directly. |
| Candidate | A structured, unpublished resource with proposed claims + evidence, stored under `source/candidates/*.yaml`, validated against `schema/candidate.schema.json`. |
| Claim | One independently testable fact (`schema/candidate.schema.json#/$defs/claim`). Each claim has its own evidence and its own status — never one record-wide checkbox. |
| Evidence | A source's contribution to one specific claim (`#/$defs/evidence`): URL, publisher, retrieval timestamp, tier, directness, chain, supports/contradicts. |
| Primary source | Has direct authority over a specific claim type (e.g. an org's site for its own phone number). Primacy does not imply correctness or currency. |
| Independent source | Did not copy its data from another source in the same corroboration set. Two directories importing one government feed are **one** evidence chain, tracked via `chain_id`. |
| Material claim | Could meaningfully affect how someone uses the resource (identity, services, phone, website, address, confidential status, operating status, hours, eligibility, cost, coverage, delivery method, accessibility, languages, closure). |
| Essential claim | The minimum material claims required for the resource to be safe/useful: identity, service offered, ≥1 working contact method, operating status, geographic coverage, privacy classification. |
| Corroborated | ≥2 independent evidence chains support the same value. |
| Contradicted | Credible evidence supports incompatible values, unresolved. |
| Uncertain | Evidence exists but cannot support a value strongly enough to pass policy. |
| Quarantined | Preserved with full evidence/audit history but blocked from publication. |
| Published record | Passed research, independent verification, deterministic policy, CI, deployment, and post-deployment verification. |

## Workflow state machine

Enforced in `scripts/workflow_state.py`. 19 linear states plus 4 shared
exception states (`quarantined`, `temporarily-suppressed`, `rejected`,
`system-paused`), reachable from any working state, never skipped forward:

```
lead-received -> intake-classified -> duplicate-checked
  -> research-a-locked -> research-b-locked -> evidence-compared
  -> verified -> risk-verification-complete -> policy-checked
  -> trust-scored -> decision-signed -> yaml-created -> pr-opened
  -> ci-passed -> merged -> deployed -> production-verified
  -> monitoring -> reverification-due -> (loops back to duplicate-checked)
```

Each edge has an explicit allowed-role set (`ROLE_FOR_TRANSITION`). An agent
whose role is not listed for an edge cannot make that transition — this is
checked in code, not left to a prompt. `DISTINCT_FROM` additionally blocks
the same *agent identity* from occupying two roles that must be separated
(researcher ≠ verifier ≠ director ≠ publisher; see "No agent may research,
verify, approve, publish, and merge the same record").

## Claim verification statuses

Exactly one of: `verified`, `verified-with-limitation`, `contradicted`,
`uncertain`, `stale`, `not-found`, `not-applicable`, `unsafe-to-publish`.

Only `verified`, `verified-with-limitation`, and legitimate `not-applicable`
may appear in an authorized publication. Any essential claim in any other
status blocks normal publication (`decide_publication` in `trust_scoring.py`).

## Source tiers

| Tier | Examples | Starting authority |
|---|---|---|
| A | Official gov program page, licensing DB, org's own site/API, official closure notice | 35 |
| B | Gov-maintained directory, accredited statewide directory, official parent-org directory | 30 |
| C | Established 211 listing, reputable nonprofit directory, professional association directory | 24 |
| D | Local gov partner page, community foundation, news, partner referral | 17 |
| E | Public submission, unconfirmed email, community report, user correction | 8 |
| F | Search snippet, social post, aggregated listing, AI summary, scrape | 2 |

A tier is scored **per claim type** — an org's website is Tier A for its own
phone number, not necessarily for its regulatory license status.

## Claim trust score (0-100)

`score_claim()` in `trust_scoring.py`:

| Component | Max | Rule |
|---|---|---|
| Source authority | 35 | Strongest single supporting source's tier value. Never additive across sources. |
| Directness | 20 | 20 explicit / 15 strong / 8 indirect / 0 requires inference. |
| Freshness | 15 | 15 within preferred window, 10 within max window, 5 unclear date, 0 stale. Windows are claim-specific (`FRESHNESS_WINDOWS`): crisis 30d, operating status/hours/phone 90d, eligibility/address 180d, general/program-identity 365d. |
| Independent corroboration | 15 | 15 if ≥2 distinct evidence chains agree with known independence, 8 if independence unknown, 0 if <2 chains. |
| Evidence-chain independence | 10 | 10 fully independent chains, 5 partial/uncertain, 0 single chain. |
| Retrieval integrity | 5 | 5 timestamped+hashed/archived, 3 timestamped only, 0 unreachable/unattributed. |

### Hard caps (applied after the raw sum; the **minimum** of all applicable caps wins)

| Condition | Cap |
|---|---|
| Only one evidence source | 79 |
| Only unofficial secondary sources (Tier D only, not E/F alone) | 69 |
| Only unverified submissions (Tier E only) | 39 |
| Only discovery sources (Tier F only) | 25 |
| Source independence unknown | 74 |
| Source is stale | 49 |
| Unresolved material conflict | 49, and the claim cannot reach `verified` |
| Evidence URL cannot be reopened | 39 |
| Claim requires inference | 39 |
| Confidential-address safety uncertain | 0 (for that claim) |
| Evidence fabricated/manipulated | 0 + `system-pause-required` incident |

## Record trust score

```
record_trust = floor(0.70 * lowest_essential_claim_score + 0.30 * weighted_avg_material_claim_score)
```

Implemented in `score_record()`. The weakest essential claim dominates the
record score by design — a high average can never hide it (see
`test_weak_essential_claim_drags_down_record`).

## Publication thresholds

| Risk tier | Record min | Essential claim min | Extra requirements |
|---|---|---|---|
| Low | 80 | 75 | ≥1 Tier A/B source; independent corroboration on operating status + primary contact |
| Elevated | 90 | 85 | 2 verifiers, unanimous; current Tier A/B source; enhanced privacy checks |
| Critical/confidential | 95 | 90 | 3 research packages, 2 verifiers unanimous; explicit confidential-location analysis; short reverification cycle |

Passing the number is necessary, not sufficient — `decide_publication()` also
requires privacy/duplicate/schema/geographic checks to pass and zero
unresolved material conflicts, regardless of score.

## Conflict handling

Never resolved by frequency, recency alone, "official-looking" source, or
lowering the threshold. `scripts/trust_scoring.py` encodes the penalty table;
the 8-step resolution procedure (normalize → identify evidence chain →
compare authority → compare directness → compare freshness → seek a
resolving source → reverify independently → decide) is a process constraint
executed by re-entering `duplicate-checked` via `reverification-due`, not a
score adjustment. Rejected values are preserved in `conflicts[].values`, never
deleted.

| Conflict kind | Penalty |
|---|---|
| Wording only | 0-5 |
| Nonessential detail | 5-10 |
| Hours/eligibility/coverage | 20 |
| Phone/address/status | 30 |
| Closure evidence | 40 |
| Privacy/safety | eligibility forced `false`, independent of score |

## Decision artifact & signature

`decide_publication()` produces an unsigned decision; `sign_decision()`
hashes the candidate's claims (minus derived score/status fields) plus the
decision (minus signature metadata) into a sha256 digest. This is an
**integrity signature, not a cryptographic identity signature** — it proves
the decision matches the exact evidence it claims to, and that nothing was
edited afterward. CI (`scripts/validate_candidate.py`, wired into
`.github/workflows/candidate-verification.yml`) recomputes it independently
on every PR and push touching `source/candidates/**`, and fails the build on
any mismatch — see `test_signature_invalidated_by_modified_claim` and
`test_adding_evidence_after_signing_invalidates_signature`.

## Hard gates enforced regardless of score

- Privacy/confidential-location failure → `quarantined`, never merely scored down.
- Duplicate, schema, or geographic-coverage failure → blocks `publication-authorized`.
- Any essential claim not in `{verified, verified-with-limitation, not-applicable}` → blocks.
- Any unresolved material conflict → blocks.
- A candidate whose `workflow_state` has reached `pr-opened` or later must have
  `decision.outcome == publication-authorized` — enforced by
  `validate_candidate.py`'s `PUBLISHED_STATES` check, independent of what any
  agent claims.

## Examples

The former Corbin United Effort development candidate and synthetic passing
fixture were backed up and removed during the clean resource reset. Neither
is an active candidate or evidence of completed independent research.
New tests must start with a fresh lead and actual research observations.
