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
leads/runs/<zip>/       ← AI discovers leads
      ↓
source/candidates/      ← AI writes candidate YAML (PR opened)
      ↓  CI: validate + recompute-decision
source/approved/        ← human approves PR; candidate promoted to approved record
```

## Rules

- AI agents write here and open PRs; they never write directly to `source/approved/`.
- CI runs `scripts/validate_candidate.py --all` on every PR touching this directory.
  Trust scores are recomputed from raw evidence; the agent's own decision is not trusted.
- A candidate may only move to `source/approved/` after `workflow_state` reaches
  `publication-authorized` and a human approves the PR.
- Quarantined or rejected candidates stay here with their terminal state for audit.
  Never delete them.
