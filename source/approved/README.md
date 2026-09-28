# source/approved/

Canonical published resource records. **These are the only records that appear on the public website.**

## Structure

```
source/approved/
├── national/           ← resources available nationwide (988, 211, etc.)
│   └── 988-lifeline.yaml
├── laurel-ky/          ← county-scoped resources
│   └── gods-pantry-food-bank.yaml
└── ...
```

## Format

Each file is a YAML resource record conforming to `schema/resource.schema.v3.json`.
The `status` field must be `active`. Only records with `verification_status` of
`verified` or `verified-with-limitation` should be here.

## Rules

- **Never edit manually.** Records arrive here via a PR from `source/candidates/`
  after human approval and CI pass.
- **Never delete manually.** Use a closure candidate (`status: closed`) instead.
- The build pipeline (`scripts/build.py`) reads only this directory to generate
  `data/resources.json` and all public HTML.
- IDs are stable once published. Never rename a file without a migration plan.
