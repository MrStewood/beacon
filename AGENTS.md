# Beacon operating policy

n8n coordinates discovery, intake, independent research, review, and publication preparation. GitHub holds durable records. GitHub Actions validates changes and builds the website. Old Python/Paperclip orchestration is retired.

## Change process

Use a branch and pull request for repository changes. Never force-push, bypass CI, approve your own publication, or merge without explicit human authorization. Every resource publication and correction requires human approval. Sensitive resources, closures, schema changes, Actions changes, and governance changes require explicit human approval as well. Credential access grants no publication authority.

## Resource integrity

Edit canonical resources only in `source/approved/`; preserve stable resource IDs and URLs. Never invent facts, verification dates, or service areas. Keep unknown facts unknown. Search snippets and AI summaries are discovery clues, never verification evidence. Website checks are not direct provider confirmation. Do not infer closure from one failed website or unanswered call. Never commit secrets, confidential locations, or individual client/help-seeker information.

## Independence and validation

Retain `scripts/workflow_state.py`, `trust_scoring.py`, and `validate_candidate.py` as deterministic enforcement. Research A and B must have isolated contexts until both packages are locked. Discovery, verification, decision signing, and publication must obey the distinct-actor rules in the state machine. n8n must invoke or obtain these checks before advancing; workflow prompts alone do not enforce them. Required checks must pass before merging. Run `python3 scripts/build.py --test` before proposing publication.

## Durable state

Read `operations/README.md`. One file in `operations/leads/` owns each lead's queue status. Candidate progression belongs to the linked candidate's `workflow_state`; evidence artifacts do not own active status. All reads in one n8n run stay pinned to its resolved commit. Writes must compare the current blob SHA, preserve audit history, and stop on conflicts. Record explicit human authorization before publication.

The repository currently commits generated public data and checks it against YAML. Until the separate CI migration removes this duplication, regenerate these outputs with the official build; never edit them manually.
