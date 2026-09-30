# n8n resource operations

- `config.json`: explicit discovery ZIP scope, service priorities, pause switch, claim expiry, and reverification intervals. Validate against `schema/operations.schema.json`. Claim acquisition and reverification scheduling are not implemented yet.
- Lead records use stable `lead-<20 hex>.json` filenames and `schema/lead.schema.json`. IDs survive name, phone, domain, and address changes.
- **Buckets (directory = lifecycle):**
  - `inbox/` — active work (`queued`, `researching`, `candidate`). Only `queued` is intake-eligible.
  - `resolved/` — closed as already published / duplicate of `source/approved/` (`published` + `resource_id`).
  - `rejected/` — will-not-pursue (`rejected` + audit reason).
  - `held/` — rare extreme/ambiguous human holds (`needs-review`, `awaiting-human`).
- Move the file when the outcome changes; do not leave copies in two buckets. Keep `status` inside the JSON aligned with the bucket.
- `source/candidates/<county>/<candidate_id>.yaml`: research/review progression once a lead has `status: candidate` and `candidate_id`.
- Legacy `leads/investigations/`, `leads/reviews/`, `leads/rejected/`, and batches: historical evidence only, not queue state.

A published lead in `resolved/` is terminal queue history; reverify through a new linked update candidate. Never publish observations directly.

Writes use GitHub APIs with a commit-pinned read and current blob SHA conflict checks. Claims identify execution and actor with an expiry; persist acquisition before work and completion after work. Acquisition is not yet implemented. Record audit events. Shared domains/phones indicate possible relationships, not duplicates. Routine `same_as_approved` intake may auto-move inbox → resolved without human review; ambiguous matches go to `held/`.

Files excluded from the website are still visible in this public repository. Store confidential operational material separately.
