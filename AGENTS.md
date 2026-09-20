# Beacon Agent Rules

## Mission

Maintain an accurate, safe, transparent community-resource directory using traceable evidence and independent review.

## Git Rules

- Never commit directly to `main`.
- Work only on a feature branch.
- Use one branch per assigned issue.
- Use the isolated worktree supplied for the task.
- Never force-push.
- Never bypass tests.
- Never use administrator merge options.
- Never approve or merge your own pull request.
- Stop and mark the task blocked when required evidence is unavailable.

## Data Rules

- Edit only canonical source records in `source/` directory.
- Never edit generated JSON, CSV, HTML, GeoJSON, sitemap, or print files manually.
- Regenerate all outputs through the official build command: `python scripts/build.py`
- Never invent a phone number, address, service, eligibility rule, verification date, or service area.
- Use null, unknown, or needs-review when facts cannot be established.
- Do not treat a search snippet or AI summary as authoritative evidence.
- Do not describe a website check as direct provider confirmation.
- Do not publish a confidential location.
- Never include information about individual clients or help seekers.
- Preserve stable resource IDs and legacy URLs.
- Do not mark a resource closed based on one broken website or unanswered call.

## Separation of Duties (code-enforced, not advisory)

`scripts/workflow_state.py` enforces every rule below in code. An agent
identity that already acted in one role is technically blocked
(`IllegalTransition`) from acting in a role listed in `DISTINCT_FROM` for it —
this is not a prompt instruction an agent could choose to ignore.

- Research Agent A and Research Agent B must work independently: neither may
  read the other's notes/conclusions before both `research_packages` are
  locked.
- The discovering agent cannot verify the same candidate.
- The verifying agent cannot approve, publish, or merge it.
- The Resource Operations Director who signs the decision (`scripts/sign_candidate.py`)
  must be distinct from every researcher and verifier on that candidate.
- The publishing agent cannot approve its own PR (also enforced by GitHub
  branch protection on `main`: 1 required approving review + required status
  checks `validate` and `recompute-decision`).
- Sensitive resources require human approval.
- No claim may move to `verified`/`verified-with-limitation` on the strength
  of an agent's own restated conclusion; `scripts/validate_candidate.py`
  independently recomputes every score from the raw evidence and fails the
  build if the committed decision does not match.

## Pull Request Rules

Every PR must include:

- Paperclip issue ID
- Candidate issue reference
- Resource IDs changed
- Fields changed
- Evidence supporting each change
- Verification method
- Remaining uncertainty
- Sensitive-resource considerations
- Tests and build commands run

Move work into review only when CI passes.

## Sensitive Resource Handling

The following require explicit human approval before publication:

- 911, 988, or 211 resources
- Crisis hotlines
- Domestic violence services
- Children's services
- Medical or treatment intake
- Confidential shelter locations
- Resource closures
- Schema changes
- GitHub Actions changes
- License or governance changes
