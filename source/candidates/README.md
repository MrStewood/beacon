# source/candidates/

In-progress resource candidates undergoing research and verification.
**These never appear on the public website** — only `source/approved/` records are built.

## Structure

```
source/candidates/
├── laurel-ky/
│   └── candidate-gods-pantry-001.yaml
└── ...
```

## Format

Each file is a candidate record conforming to `schema/candidate.schema.json`.
It carries full claim/evidence/decision metadata plus the embedded resource draft.

## Lifecycle

```
operations/ inbox leads   ← discovery / intake
      ↓
source/candidates/        ← research candidate YAML on main
      ↓  CI on push: validate + recompute-decision
source/approved/          ← human-authorized promotion on main
```

## Rules

- Authorized automation may write candidates directly on `main`.
- Do not write directly to `source/approved/` without explicit human publication authorization.
- CI runs `scripts/validate_candidate.py --all` on pushes touching this directory.
  Trust scores are recomputed from raw evidence; the agent's own decision is not trusted.
- A candidate may only move to `source/approved/` after `workflow_state` reaches
  `publication-authorized` and a human authorizes that publication commit.
- Quarantined or rejected candidates stay here with their terminal state for audit.
  Never delete them.
