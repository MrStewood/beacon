# Governance

[AGENTS.md](AGENTS.md) defines change authorization. n8n prepares work; independent roles validate it; a human authorizes publication into `source/approved/`. Commits go directly to `main` (no pull-request requirement). All public resource publications require human authorization. Resolve evidence disputes and unsafe changes with the human publisher. Roll back with a revert commit on `main`, then verify deployment.
