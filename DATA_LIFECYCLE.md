# Beacon Data Lifecycle

## Record States

| State | Description |
|-------|-------------|
| `discovered` | Found by research agent, not yet verified |
| `researching` | Under active research |
| `awaiting-verification` | Ready for independent verification |
| `verified` | Confirmed by independent verifier |
| `approved` | Ready for publication |
| `published` | Live on the public site |
| `needs-review` | Requires attention |
| `closed` | Service no longer available (requires evidence) |
| `superseded` | Replaced by another record |

## Lifecycle Rules

### Discovery → Verification
- Different agents must handle discovery and verification
- Evidence must be documented before verification

### Verification → Publication
- Requires human approval for sensitive resources
- CI must pass
- Changed-record report must be generated

### Re-verification
- `verified` records: reverify annually
- `website-checked`: reverify every 6 months
- `source-only`: reverify quarterly

### Closure
- Requires evidence (not just broken website)
- Human approval required
- Never auto-close based on single failed check

### Supersession
- Old record marked `superseded`
- New record created with `related` field pointing to old
- Old record preserved for history

## Audit Trail

Every change is tracked through:
- Git history
- Pull request descriptions
- Workflow metadata in YAML files
- Changed-record reports
