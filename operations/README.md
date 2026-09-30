# n8n resource operations

- `config.json`: explicit discovery ZIP scope, service priorities, pause switch, claim expiry, and reverification intervals. Validate against `schema/operations.schema.json`. Claim acquisition and reverification scheduling are not implemented yet.
- `leads/<lead_id>.json`: stable identity and authoritative queue status, validated against `schema/lead.schema.json`. IDs survive name, phone, domain, and address changes. Migration IDs were generated once from old queue keys; new intake should generate a random 20-hex suffix and preserve it thereafter.
- `source/candidates/<county>/<candidate_id>.yaml`: authoritative research/review progression once a lead has `status: candidate` and `candidate_id`. Link the candidate back through `lead_id` (supported by the candidate schema). Published resource IDs are preserved.
- `leads/investigations/`, `leads/reviews/`, `leads/rejected/`, and lead batches: historical observations and evidence, not queue state. Name-based migration links require confirmation during intake. Imported `published` means a matching approved record exists; it is not a new verification claim.

Queue statuses: queued, researching, needs-review, awaiting-human, candidate, published, rejected. Only queued records are intake tasks. A candidate owns subsequent workflow progression. A published lead is terminal queue history; reverify through a new linked update candidate. Never publish observations directly.

Writes use GitHub APIs with a commit-pinned read and current blob SHA conflict checks. Claims identify execution and actor with an expiry; persist acquisition before work and completion after work. Acquisition is not yet implemented. Record audit events and approval artifacts. Shared domains/phones indicate possible relationships, not duplicates.

Files excluded from the website are still visible in this public repository. Store confidential operational material separately.
