# Resource lifecycle

Lead queue statuses and candidate ownership are defined in operations/README.md. Candidate progression follows schema/candidate.schema.json and scripts/workflow_state.py. Approval, merge, deployment, and production verification are separate states. Reverification intervals are configured in operations/config.json; their scheduling is not implemented yet. Preserve evidence and audit history. Closure and publication require human authorization.
